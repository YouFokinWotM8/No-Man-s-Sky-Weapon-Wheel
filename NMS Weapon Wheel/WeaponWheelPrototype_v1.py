"""
No Man's Sky radial multitool wheel for pyMHF / NMS.py.

Controls:
    Hold G  -> open wheel
    Move mouse -> highlight wedge
    Release G -> select highlighted item

F8 remains as an unsuppressed fallback while G takeover is being tested.

This build:
- primary + secondary native setters
- dynamic mode-table filtering
- modes 9 and 10 filtered
- shaped Win32 wheel window: no rectangular background
- G is intercepted only while NMS is the foreground application
"""

import ctypes
import logging
import math
import queue
import threading

import keyboard

from pymhf import Mod
from pymhf.core.hooking import on_key_pressed, on_key_release
from pymhf.gui.decorators import STRING, gui_button
import nmspy.data.types as nms


logger = logging.getLogger()


# ===========================================================================
# NMS signatures / dynamically resolved layout
# ===========================================================================

# No build-specific RVAs are used here.  These signatures are matched against
# the loaded NMS.exe .text section.  Update-sensitive displacements/offsets are
# wildcarded and then recovered from the matching instructions.

GLOBAL_STATE_SIGNATURE = (
    "48 89 5C 24 10 "
    "48 89 6C 24 18 "
    "56 "
    "48 83 EC 20 "
    "4C 8B 05 ?? ?? ?? ?? "
    "48 8B E9 "
    "33 F6 "
    "48 89 7C 24 30 "
    "8B 9D ?? ?? ?? ??"
)

PRIMARY_SETTER_SIGNATURE = (
    "48 89 5C 24 20 "
    "57 "
    "48 83 EC 60 "
    "48 63 DA "
    "48 8B F9 "
    "8B D3 "
    "E8 ?? ?? ?? ?? "
    "84 C0 "
    "0F 84 ?? ?? ?? ?? "
    "48 63 87 ?? ?? ?? ??"
)

SECONDARY_SETTER_SIGNATURE = (
    "48 89 5C 24 08 "
    "48 89 6C 24 10 "
    "48 89 74 24 18 "
    "57 "
    "48 83 EC 20 "
    "48 8B 35 ?? ?? ?? ?? "
    "48 8B D9 "
    "8B A9 ?? ?? ?? ?? "
    "48 63 FA "
    "8B C7 "
    "44 8B C7 "
    "99 "
    "41 83 E0 1F "
    "83 E2 1F "
    "03 C2 "
    "C1 F8 05"
)

PENDING_MODE_SIGNATURE = (
    "C7 87 ?? ?? ?? ?? 15 00 00 00 "
    "EB ?? "
    "89 9F ?? ?? ?? ??"
)

MODE_TABLE_SIGNATURE = (
    "48 8B C7 "
    "48 03 C0 "
    "80 BC C6 ?? ?? ?? ?? 00"
)

WEAPON_WRAPPER_SIGNATURE = (
    "40 53 "
    "48 83 EC 20 "
    "48 8B D9 "
    "48 8B 0D ?? ?? ?? ?? "
    "83 B9 ?? ?? ?? ?? 02 "
    "74 ?? "
    "48 81 C1 ?? ?? ?? ?? "
    "E8 ?? ?? ?? ?? "
    "83 F8 01 "
    "7E ?? "
    "48 8B CB "
    "48 83 C4 20 "
    "5B "
    "E9 ?? ?? ?? ??"
)

MODE_TABLE_STRIDE = 0x10

MODE_SCAN_FIRST = 0
MODE_SCAN_LAST = 20

_NMS_LAYOUT = None
_NMS_LAYOUT_LOCK = threading.Lock()


# ===========================================================================
# Mode mappings
# ===========================================================================

FILTERED_INTERNAL_MODES = {
    9,
    10,
}


PRIMARY_MODE_NAMES = {
    0: "Boltcaster",
    1: "Scatter Blaster",
    2: "Pulse Spitter",
    3: "Blaze Javelin",
    5: "Mining Beam",
    11: "Terrain Manipulator",
    19: "Fishing Rig",
    20: "Gravitino Coil",
}


SECONDARY_MODE_NAMES = {
    6: "Plasma Launcher",
    7: "Geology Cannon",
    17: "Paralysis Mortar",
}


WHEEL_ORDER = [
    ("primary", 5),
    ("primary", 0),
    ("primary", 1),
    ("primary", 2),
    ("primary", 3),

    ("secondary", 6),
    ("secondary", 7),
    ("secondary", 17),

    ("primary", 11),
    ("primary", 19),
    ("primary", 20),
]


# ===========================================================================
# Native setter declarations
# ===========================================================================

_SetWeaponModeProto = ctypes.WINFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_int32,
)


# ===========================================================================
# Win32
# ===========================================================================

_kernel32 = ctypes.WinDLL(
    "kernel32",
    use_last_error=True,
)

_user32 = ctypes.WinDLL(
    "user32",
    use_last_error=True,
)

_gdi32 = ctypes.WinDLL(
    "gdi32",
    use_last_error=True,
)


_kernel32.GetModuleHandleW.argtypes = [
    ctypes.c_wchar_p,
]

_kernel32.GetModuleHandleW.restype = ctypes.c_void_p


_kernel32.GetCurrentProcessId.argtypes = []

_kernel32.GetCurrentProcessId.restype = ctypes.c_uint32


_kernel32.GetCurrentProcess.argtypes = []

_kernel32.GetCurrentProcess.restype = ctypes.c_void_p


_kernel32.ReadProcessMemory.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]

_kernel32.ReadProcessMemory.restype = ctypes.c_bool


# ===========================================================================
# Win32 structs
# ===========================================================================

class POINT(ctypes.Structure):

    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class RECT(ctypes.Structure):

    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


# ===========================================================================
# Win32 function declarations
# ===========================================================================

_user32.GetCursorPos.argtypes = [
    ctypes.POINTER(POINT),
]

_user32.GetCursorPos.restype = ctypes.c_bool


_user32.SetCursorPos.argtypes = [
    ctypes.c_int,
    ctypes.c_int,
]

_user32.SetCursorPos.restype = ctypes.c_bool


_user32.IsWindowVisible.argtypes = [
    ctypes.c_void_p,
]

_user32.IsWindowVisible.restype = ctypes.c_bool


_user32.GetClientRect.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(RECT),
]

_user32.GetClientRect.restype = ctypes.c_bool


_user32.ClientToScreen.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(POINT),
]

_user32.ClientToScreen.restype = ctypes.c_bool


_user32.GetWindowThreadProcessId.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint32),
]

_user32.GetWindowThreadProcessId.restype = ctypes.c_uint32


_user32.GetForegroundWindow.argtypes = []

_user32.GetForegroundWindow.restype = ctypes.c_void_p


_user32.GetParent.argtypes = [
    ctypes.c_void_p,
]

_user32.GetParent.restype = ctypes.c_void_p


_user32.SetWindowPos.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]

_user32.SetWindowPos.restype = ctypes.c_bool


WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool,
    ctypes.c_void_p,
    ctypes.c_void_p,
)


_user32.EnumWindows.argtypes = [
    WNDENUMPROC,
    ctypes.c_void_p,
]

_user32.EnumWindows.restype = ctypes.c_bool


# ===========================================================================
# Window styles
# ===========================================================================

GWL_EXSTYLE = -20

WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

# Position the overlay with native Win32 coordinates instead of relying on
# Tk's multi-monitor/DPI geometry translation.
HWND_TOPMOST = ctypes.c_void_p(-1).value
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200


_user32.GetWindowLongW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
]

_user32.GetWindowLongW.restype = ctypes.c_long


_user32.SetWindowLongW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_long,
]

_user32.SetWindowLongW.restype = ctypes.c_long


# ===========================================================================
# Window-region functions
# ===========================================================================

WINDING = 2
RGN_OR = 2


_gdi32.CreateRectRgn.argtypes = [
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
]

_gdi32.CreateRectRgn.restype = ctypes.c_void_p


_gdi32.CreateEllipticRgn.argtypes = [
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
]

_gdi32.CreateEllipticRgn.restype = ctypes.c_void_p


_gdi32.CreatePolygonRgn.argtypes = [
    ctypes.POINTER(POINT),
    ctypes.c_int,
    ctypes.c_int,
]

_gdi32.CreatePolygonRgn.restype = ctypes.c_void_p


_gdi32.CombineRgn.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_int,
]

_gdi32.CombineRgn.restype = ctypes.c_int


_gdi32.DeleteObject.argtypes = [
    ctypes.c_void_p,
]

_gdi32.DeleteObject.restype = ctypes.c_bool


_user32.SetWindowRgn.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_bool,
]

_user32.SetWindowRgn.restype = ctypes.c_int


# Preserve our direct G hook handle across pyMHF reloads if possible.
_G_BLOCK_HOOK = globals().get(
    "_G_BLOCK_HOOK",
    None,
)


# ===========================================================================
# Win32 helpers
# ===========================================================================

def _find_game_client_rect():

    current_pid = (
        _kernel32.GetCurrentProcessId()
    )

    matches = []


    @WNDENUMPROC
    def enum_proc(
        hwnd,
        _lparam,
    ):

        try:

            if not _user32.IsWindowVisible(
                hwnd
            ):
                return True


            pid = ctypes.c_uint32(
                0
            )


            _user32.GetWindowThreadProcessId(
                hwnd,
                ctypes.byref(pid),
            )


            if (
                pid.value
                != current_pid
            ):
                return True


            rect = RECT()


            if not _user32.GetClientRect(
                hwnd,
                ctypes.byref(rect),
            ):
                return True


            width = (
                rect.right
                - rect.left
            )

            height = (
                rect.bottom
                - rect.top
            )


            if (
                width < 400
                or height < 300
            ):
                return True


            origin = POINT(
                0,
                0,
            )


            if not _user32.ClientToScreen(
                hwnd,
                ctypes.byref(origin),
            ):
                return True


            matches.append(
                (
                    width * height,
                    int(origin.x),
                    int(origin.y),
                    int(width),
                    int(height),
                )
            )


        except Exception:
            pass


        return True


    _user32.EnumWindows(
        enum_proc,
        None,
    )


    if not matches:

        raise RuntimeError(
            "Could not find the visible NMS game window."
        )


    matches.sort(
        reverse=True
    )


    (
        _area,
        left,
        top,
        width,
        height,
    ) = matches[0]


    return (
        left,
        top,
        width,
        height,
    )


def _is_nms_foreground():

    hwnd = (
        _user32.GetForegroundWindow()
    )


    if not hwnd:
        return False


    pid = ctypes.c_uint32(
        0
    )


    _user32.GetWindowThreadProcessId(
        hwnd,
        ctypes.byref(pid),
    )


    return (
        pid.value
        ==
        _kernel32.GetCurrentProcessId()
    )


def _get_cursor_pos():

    point = POINT()


    if not _user32.GetCursorPos(
        ctypes.byref(point)
    ):

        raise RuntimeError(
            "GetCursorPos failed."
        )


    return (
        int(point.x),
        int(point.y),
    )


# ===========================================================================
# Weapon backend
# ===========================================================================

def _entry_name(
    kind,
    native_id,
):

    if kind == "primary":

        return PRIMARY_MODE_NAMES.get(
            native_id,
            f"Unknown primary {native_id}",
        )


    return SECONDARY_MODE_NAMES.get(
        native_id,
        f"Unknown secondary {native_id}",
    )


def _read_process_memory(
    address,
    size,
):

    address = int(address)
    size = int(size)


    if address <= 0:

        raise RuntimeError(
            f"Refusing to read invalid address 0x{address:X}."
        )


    if size <= 0 or size > 0x20000000:

        raise RuntimeError(
            f"Refusing unreasonable memory read size 0x{size:X}."
        )


    buffer = ctypes.create_string_buffer(
        size
    )

    bytes_read = ctypes.c_size_t(
        0
    )

    process = (
        _kernel32.GetCurrentProcess()
    )


    ok = _kernel32.ReadProcessMemory(
        process,
        ctypes.c_void_p(address),
        ctypes.cast(
            buffer,
            ctypes.c_void_p,
        ),
        size,
        ctypes.byref(bytes_read),
    )


    if (
        not ok
        or bytes_read.value != size
    ):

        error = ctypes.get_last_error()

        raise RuntimeError(
            "Safe memory read failed at "
            f"0x{address:X} for 0x{size:X} bytes "
            f"(read=0x{bytes_read.value:X}, winerr={error})."
        )


    return buffer.raw


def _read_u8(
    address,
):

    return _read_process_memory(
        address,
        1,
    )[0]


def _read_i32(
    address,
):

    return int.from_bytes(
        _read_process_memory(
            address,
            4,
        ),
        "little",
        signed=True,
    )


def _read_u32(
    address,
):

    return int.from_bytes(
        _read_process_memory(
            address,
            4,
        ),
        "little",
        signed=False,
    )


def _read_i32_blob(
    blob,
    offset,
):

    return int.from_bytes(
        blob[
            offset:
            offset + 4
        ],
        "little",
        signed=True,
    )


def _read_u32_blob(
    blob,
    offset,
):

    return int.from_bytes(
        blob[
            offset:
            offset + 4
        ],
        "little",
        signed=False,
    )


def _read_pointer(
    address,
):

    return int.from_bytes(
        _read_process_memory(
            address,
            ctypes.sizeof(
                ctypes.c_void_p
            ),
        ),
        "little",
        signed=False,
    )


def _compile_signature(
    signature,
):

    values = bytearray()
    mask = bytearray()


    for token in signature.split():

        if token in {
            "?",
            "??",
        }:

            values.append(
                0
            )

            mask.append(
                0
            )

        else:

            values.append(
                int(
                    token,
                    16,
                )
            )

            mask.append(
                1
            )


    return (
        bytes(values),
        bytes(mask),
    )


def _signature_matches(
    data,
    offset,
    values,
    mask,
):

    end = (
        offset
        + len(values)
    )


    if (
        offset < 0
        or end > len(data)
    ):

        return False


    for index in range(
        len(values)
    ):

        if (
            mask[index]
            and data[
                offset + index
            ] != values[index]
        ):

            return False


    return True


def _find_signature_offsets(
    data,
    signature,
):

    (
        values,
        mask,
    ) = _compile_signature(
        signature
    )


    best_start = -1
    best_length = 0
    run_start = 0
    run_length = 0


    for index in range(
        len(mask) + 1
    ):

        literal = (
            index < len(mask)
            and mask[index]
        )


        if literal:

            if run_length == 0:
                run_start = index

            run_length += 1

        else:

            if run_length > best_length:

                best_start = run_start
                best_length = run_length


            run_length = 0


    if best_length <= 0:

        raise RuntimeError(
            "Signature contains no literal bytes."
        )


    anchor = values[
        best_start:
        best_start + best_length
    ]

    matches = []
    search_from = 0


    while True:

        found = data.find(
            anchor,
            search_from,
        )


        if found < 0:
            break


        candidate = (
            found
            - best_start
        )


        if _signature_matches(
            data,
            candidate,
            values,
            mask,
        ):

            matches.append(
                candidate
            )


        search_from = (
            found + 1
        )


    return matches


def _find_unique_signature(
    text_bytes,
    text_base,
    name,
    signature,
):

    matches = _find_signature_offsets(
        text_bytes,
        signature,
    )


    if len(matches) != 1:

        raise RuntimeError(
            f"Unsupported NMS build: {name} signature "
            f"matched {len(matches)} locations; expected exactly 1."
        )


    offset = matches[0]


    return (
        text_base + offset,
        offset,
    )


def _get_text_section(
    module_base,
):

    header = _read_process_memory(
        module_base,
        0x1000,
    )


    if header[0:2] != b"MZ":

        raise RuntimeError(
            "Unsupported NMS build: NMS.exe has no valid MZ header."
        )


    pe_offset = _read_u32_blob(
        header,
        0x3C,
    )


    if (
        pe_offset < 0x40
        or pe_offset > 0x100000
    ):

        raise RuntimeError(
            f"Unsupported NMS build: invalid PE offset 0x{pe_offset:X}."
        )


    minimum_header_size = (
        pe_offset
        + 24
    )


    if minimum_header_size > len(header):

        header = _read_process_memory(
            module_base,
            minimum_header_size,
        )


    if header[
        pe_offset:
        pe_offset + 4
    ] != b"PE\x00\x00":

        raise RuntimeError(
            "Unsupported NMS build: NMS.exe has no valid PE signature."
        )


    number_of_sections = int.from_bytes(
        header[
            pe_offset + 6:
            pe_offset + 8
        ],
        "little",
    )

    size_of_optional_header = int.from_bytes(
        header[
            pe_offset + 20:
            pe_offset + 22
        ],
        "little",
    )

    section_table = (
        pe_offset
        + 24
        + size_of_optional_header
    )

    full_header_size = (
        section_table
        + number_of_sections * 40
    )


    if full_header_size > len(header):

        header = _read_process_memory(
            module_base,
            full_header_size,
        )


    for index in range(
        number_of_sections
    ):

        section = (
            section_table
            + index * 40
        )

        name = header[
            section:
            section + 8
        ].split(
            b"\x00",
            1,
        )[0]


        if name != b".text":
            continue


        virtual_size = _read_u32_blob(
            header,
            section + 8,
        )

        virtual_address = _read_u32_blob(
            header,
            section + 12,
        )

        raw_size = _read_u32_blob(
            header,
            section + 16,
        )

        text_size = (
            virtual_size
            or raw_size
        )


        if (
            virtual_address <= 0
            or text_size <= 0
            or text_size > 0x20000000
        ):

            raise RuntimeError(
                "Unsupported NMS build: invalid .text section bounds."
            )


        text_base = (
            module_base
            + virtual_address
        )

        text_bytes = _read_process_memory(
            text_base,
            text_size,
        )


        return (
            text_base,
            text_bytes,
        )


    raise RuntimeError(
        "Unsupported NMS build: could not locate NMS.exe .text section."
    )


def _verify_signature_at(
    address,
    name,
    signature,
):

    (
        values,
        mask,
    ) = _compile_signature(
        signature
    )

    actual = _read_process_memory(
        address,
        len(values),
    )


    if not _signature_matches(
        actual,
        0,
        values,
        mask,
    ):

        raise RuntimeError(
            f"{name} signature changed after resolution; native call refused."
        )


def _resolve_nms_layout():

    global _NMS_LAYOUT


    with _NMS_LAYOUT_LOCK:

        if _NMS_LAYOUT is not None:

            return _NMS_LAYOUT


        module_base = int(
            _kernel32.GetModuleHandleW(
                "NMS.exe"
            )
            or 0
        )


        if not module_base:

            raise RuntimeError(
                "Could not resolve loaded NMS.exe module base."
            )


        (
            text_base,
            text_bytes,
        ) = _get_text_section(
            module_base
        )


        (
            global_match,
            global_offset,
        ) = _find_unique_signature(
            text_bytes,
            text_base,
            "global-state",
            GLOBAL_STATE_SIGNATURE,
        )

        (
            primary_setter_address,
            primary_offset,
        ) = _find_unique_signature(
            text_bytes,
            text_base,
            "primary setter",
            PRIMARY_SETTER_SIGNATURE,
        )

        (
            secondary_setter_address,
            secondary_offset,
        ) = _find_unique_signature(
            text_bytes,
            text_base,
            "secondary setter",
            SECONDARY_SETTER_SIGNATURE,
        )

        (
            pending_match,
            pending_offset_in_text,
        ) = _find_unique_signature(
            text_bytes,
            text_base,
            "pending-primary field",
            PENDING_MODE_SIGNATURE,
        )

        (
            mode_table_match,
            mode_table_offset_in_text,
        ) = _find_unique_signature(
            text_bytes,
            text_base,
            "installed-mode table",
            MODE_TABLE_SIGNATURE,
        )

        (
            weapon_wrapper_match,
            weapon_wrapper_offset,
        ) = _find_unique_signature(
            text_bytes,
            text_base,
            "weapon-object wrapper",
            WEAPON_WRAPPER_SIGNATURE,
        )


        global_disp = _read_i32_blob(
            text_bytes,
            global_offset + 18,
        )

        global_ptr_address = (
            global_match
            + 22
            + global_disp
        )

        global_ptr_rva = (
            global_ptr_address
            - module_base
        )


        # Cross-check the secondary setter's RIP-relative global reference.
        secondary_global_disp = _read_i32_blob(
            text_bytes,
            secondary_offset + 23,
        )

        secondary_global_address = (
            secondary_setter_address
            + 27
            + secondary_global_disp
        )


        if secondary_global_address != global_ptr_address:

            raise RuntimeError(
                "Unsupported NMS build: global-state signatures disagree."
            )


        current_mode_offset_a = _read_u32_blob(
            text_bytes,
            global_offset + 34,
        )

        current_mode_offset_b = _read_u32_blob(
            text_bytes,
            primary_offset + 34,
        )


        if current_mode_offset_a != current_mode_offset_b:

            raise RuntimeError(
                "Unsupported NMS build: current-primary field offsets disagree."
            )


        secondary_mode_offset = _read_u32_blob(
            text_bytes,
            secondary_offset + 32,
        )

        pending_mode_offset_a = _read_u32_blob(
            text_bytes,
            pending_offset_in_text + 2,
        )

        pending_idle_sentinel = _read_u32_blob(
            text_bytes,
            pending_offset_in_text + 6,
        )

        pending_mode_offset_b = _read_u32_blob(
            text_bytes,
            pending_offset_in_text + 14,
        )


        if pending_mode_offset_a != pending_mode_offset_b:

            raise RuntimeError(
                "Unsupported NMS build: pending-primary field offsets disagree."
            )


        mode_table_offset = _read_u32_blob(
            text_bytes,
            mode_table_offset_in_text + 9,
        )

        weapon_object_offset = _read_u32_blob(
            text_bytes,
            weapon_wrapper_offset + 28,
        )


        # Structural checks.  These are deliberately broad: they reject obviously
        # wrong matches without tying the mod to one exact NMS build.
        object_fields = {
            current_mode_offset_a,
            pending_mode_offset_a,
            secondary_mode_offset,
        }


        if (
            len(object_fields) != 3
            or any(
                value <= 0
                or value > 0x10000
                for value in object_fields
            )
        ):

            raise RuntimeError(
                "Unsupported NMS build: resolved weapon field offsets are implausible."
            )


        if (
            pending_idle_sentinel > 0x10000
            or mode_table_offset <= 0
            or mode_table_offset > 0x1000000
            or weapon_object_offset <= 0
            or weapon_object_offset > 0x10000000
        ):

            raise RuntimeError(
                "Unsupported NMS build: resolved layout values are implausible."
            )


        if not (
            0
            < pending_match - primary_setter_address
            < 0x2000
        ):

            raise RuntimeError(
                "Unsupported NMS build: pending-primary pattern is not inside "
                "the expected primary-setter neighborhood."
            )


        if not (
            0
            < mode_table_match - secondary_setter_address
            < 0x1000
        ):

            raise RuntimeError(
                "Unsupported NMS build: mode-table pattern is not inside "
                "the expected secondary-setter neighborhood."
            )


        layout = {
            "module_base":
                module_base,

            "global_state_ptr_address":
                global_ptr_address,

            "global_state_ptr_rva":
                global_ptr_rva,

            "weapon_object_offset":
                weapon_object_offset,

            "current_mode_offset":
                current_mode_offset_a,

            "pending_mode_offset":
                pending_mode_offset_a,

            "secondary_mode_offset":
                secondary_mode_offset,

            "pending_idle_sentinel":
                pending_idle_sentinel,

            "primary_setter_address":
                primary_setter_address,

            "primary_setter_rva":
                primary_setter_address
                - module_base,

            "secondary_setter_address":
                secondary_setter_address,

            "secondary_setter_rva":
                secondary_setter_address
                - module_base,

            "mode_table_offset":
                mode_table_offset,
        }


        _NMS_LAYOUT = layout


        logger.warning(
            "[WeaponWheel] RESOLVED | "
            "global_rva=0x%X | "
            "weapon_off=0x%X | "
            "current=0x%X | "
            "pending=0x%X | "
            "secondary=0x%X | "
            "idle=%d | "
            "primary_rva=0x%X | "
            "secondary_rva=0x%X | "
            "mode_table=0x%X",
            layout["global_state_ptr_rva"],
            layout["weapon_object_offset"],
            layout["current_mode_offset"],
            layout["pending_mode_offset"],
            layout["secondary_mode_offset"],
            layout["pending_idle_sentinel"],
            layout["primary_setter_rva"],
            layout["secondary_setter_rva"],
            layout["mode_table_offset"],
        )


        return layout


def _read_weapon_state():

    layout = (
        _resolve_nms_layout()
    )

    global_state = (
        _read_pointer(
            layout[
                "global_state_ptr_address"
            ]
        )
    )


    if (
        global_state < 0x10000
        or global_state >= 0x0000800000000000
    ):

        raise RuntimeError(
            "NMS global-state pointer is null or implausible at "
            f"0x{layout['global_state_ptr_address']:X}: "
            f"0x{global_state:X}."
        )


    weapon_object = (
        global_state
        + layout[
            "weapon_object_offset"
        ]
    )

    current_mode = (
        _read_i32(
            weapon_object
            + layout[
                "current_mode_offset"
            ]
        )
    )

    pending_mode = (
        _read_i32(
            weapon_object
            + layout[
                "pending_mode_offset"
            ]
        )
    )

    secondary_mode = (
        _read_i32(
            weapon_object
            + layout[
                "secondary_mode_offset"
            ]
        )
    )


    for (
        label,
        value,
    ) in (
        (
            "current primary",
            current_mode,
        ),
        (
            "pending primary",
            pending_mode,
        ),
        (
            "secondary",
            secondary_mode,
        ),
    ):

        if not (
            -1
            <= value
            <= 0x10000
        ):

            raise RuntimeError(
                f"Resolved {label} value is implausible: {value}."
            )


    return {
        "module_base":
            layout[
                "module_base"
            ],

        "global_state":
            global_state,

        "weapon_object":
            weapon_object,

        "primary_setter_address":
            layout[
                "primary_setter_address"
            ],

        "secondary_setter_address":
            layout[
                "secondary_setter_address"
            ],

        "current_mode":
            current_mode,

        "pending_mode":
            pending_mode,

        "secondary_mode":
            secondary_mode,

        "pending_idle_sentinel":
            layout[
                "pending_idle_sentinel"
            ],

        "mode_table_offset":
            layout[
                "mode_table_offset"
            ],
    }


def _read_mode_table():

    state = (
        _read_weapon_state()
    )

    values = {}


    for mode in range(
        MODE_SCAN_FIRST,
        MODE_SCAN_LAST + 1,
    ):

        address = (
            state["global_state"]
            + state[
                "mode_table_offset"
            ]
            + (
                mode
                * MODE_TABLE_STRIDE
            )
        )

        values[mode] = (
            _read_u8(
                address
            )
        )


    return (
        state,
        values,
    )


def _get_wheel_entries():

    (
        state,
        values,
    ) = _read_mode_table()


    live_modes = {
        mode
        for (
            mode,
            value,
        )
        in values.items()
        if value != 0
    }


    entries = []


    for (
        kind,
        native_id,
    ) in WHEEL_ORDER:

        if (
            native_id
            in FILTERED_INTERNAL_MODES
        ):
            continue


        if (
            native_id
            not in live_modes
        ):
            continue


        if (
            kind == "primary"
            and native_id
            not in PRIMARY_MODE_NAMES
        ):
            continue


        if (
            kind == "secondary"
            and native_id
            not in SECONDARY_MODE_NAMES
        ):
            continue


        entries.append(
            (
                kind,
                native_id,
            )
        )


    known_modes = (
        set(
            PRIMARY_MODE_NAMES
        )
        |
        set(
            SECONDARY_MODE_NAMES
        )
        |
        FILTERED_INTERNAL_MODES
    )


    unknown = sorted(
        mode
        for mode in live_modes
        if mode not in known_modes
    )


    return (
        state,
        entries,
        unknown,
        values,
    )


def _verify_primary_setter(
    address,
):

    _verify_signature_at(
        address,
        "Primary setter",
        PRIMARY_SETTER_SIGNATURE,
    )


def _verify_secondary_setter(
    address,
):

    _verify_signature_at(
        address,
        "Secondary setter",
        SECONDARY_SETTER_SIGNATURE,
    )


# ===========================================================================
# Shaped radial overlay
# ===========================================================================

class _WheelOverlay:

    OVERLAY_SIZE = 620


    def __init__(
        self
    ):

        self._commands = (
            queue.Queue()
        )

        self._selection_lock = (
            threading.Lock()
        )

        self._selected_entry = None

        self._entries = []

        self._current_primary = None

        self._current_secondary = None

        self._saved_cursor = None


        threading.Thread(
            target=self._thread_main,
            name="NMSWeaponWheelOverlay",
            daemon=True,
        ).start()


    def show(
        self,
        entries,
        current_primary,
        current_secondary,
    ):

        self._commands.put(
            (
                "show",
                list(entries),
                current_primary,
                current_secondary,
            )
        )


    def hide(
        self
    ):

        self._commands.put(
            (
                "hide",
            )
        )


    def selected_entry(
        self
    ):

        with self._selection_lock:

            return (
                self._selected_entry
            )


    def _set_selected(
        self,
        entry,
    ):

        with self._selection_lock:

            self._selected_entry = (
                entry
            )


    def _thread_main(
        self
    ):

        try:

            import tkinter as tk


            root = tk.Tk()

            root.withdraw()

            root.overrideredirect(
                True
            )

            root.attributes(
                "-topmost",
                True,
            )


            canvas = tk.Canvas(
                root,
                highlightthickness=0,
                borderwidth=0,
                background="#0b1117",
            )


            canvas.pack(
                fill="both",
                expand=True,
            )


            state = {

                "visible":
                    False,

                "left":
                    0,

                "top":
                    0,

                "cx":
                    0.0,

                "cy":
                    0.0,

                "inner":
                    76.0,

                "outer":
                    266.0,

                "last_selected":
                    object(),
            }


            # ===============================================================
            # Click-through window
            # ===============================================================

            def apply_clickthrough():

                hwnd = (
                    root.winfo_id()
                )


                style = (
                    _user32.GetWindowLongW(
                        hwnd,
                        GWL_EXSTYLE,
                    )
                )


                style |= (
                    WS_EX_TRANSPARENT
                    |
                    WS_EX_TOOLWINDOW
                    |
                    WS_EX_NOACTIVATE
                )


                _user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    style,
                )


            # ===============================================================
            # Wedge geometry
            # ===============================================================

            def wedge_points(
                cx,
                cy,
                inner,
                outer,
                a0,
                a1,
                steps=20,
            ):

                points = []


                for i in range(
                    steps + 1
                ):

                    angle = (
                        a0
                        + (
                            a1 - a0
                        )
                        * (
                            i / steps
                        )
                    )


                    points.append(
                        (
                            cx
                            + outer
                            * math.cos(
                                angle
                            ),

                            cy
                            + outer
                            * math.sin(
                                angle
                            ),
                        )
                    )


                for i in range(
                    steps,
                    -1,
                    -1,
                ):

                    angle = (
                        a0
                        + (
                            a1 - a0
                        )
                        * (
                            i / steps
                        )
                    )


                    points.append(
                        (
                            cx
                            + inner
                            * math.cos(
                                angle
                            ),

                            cy
                            + inner
                            * math.sin(
                                angle
                            ),
                        )
                    )


                return points


            def flatten(
                points
            ):

                flat = []


                for (
                    x,
                    y,
                ) in points:

                    flat.extend(
                        (
                            x,
                            y,
                        )
                    )


                return flat


            # ===============================================================
            # Shape the actual native window
            # ===============================================================

            def apply_window_shape():

                """
                Clip the HWND to the union of the wedges and center circle.

                There is literally no native window outside this region.
                This removes the old 620x620 rectangular background.
                """

                hwnd = (
                    root.winfo_id()
                )


                combined = (
                    _gdi32.CreateRectRgn(
                        0,
                        0,
                        0,
                        0,
                    )
                )


                if not combined:

                    raise RuntimeError(
                        "CreateRectRgn failed."
                    )


                success = False


                try:

                    count = len(
                        self._entries
                    )


                    if count:

                        step = (
                            math.tau
                            / count
                        )


                        for index in range(
                            count
                        ):

                            center = (
                                -math.pi / 2.0
                                + (
                                    index
                                    * step
                                )
                            )


                            # Slightly wider than the drawn polygon
                            # so outlines never get clipped.

                            a0 = (
                                center
                                - step / 2.0
                                + 0.008
                            )

                            a1 = (
                                center
                                + step / 2.0
                                - 0.008
                            )


                            points = wedge_points(
                                state["cx"],
                                state["cy"],
                                max(
                                    0.0,
                                    state["inner"]
                                    - 3.0,
                                ),
                                state["outer"]
                                + 3.0,
                                a0,
                                a1,
                            )


                            point_array_type = (
                                POINT
                                * len(points)
                            )


                            point_array = (
                                point_array_type(
                                    *[
                                        POINT(
                                            int(
                                                round(x)
                                            ),
                                            int(
                                                round(y)
                                            ),
                                        )
                                        for (
                                            x,
                                            y,
                                        )
                                        in points
                                    ]
                                )
                            )


                            region = (
                                _gdi32.CreatePolygonRgn(
                                    point_array,
                                    len(points),
                                    WINDING,
                                )
                            )


                            if region:

                                _gdi32.CombineRgn(
                                    combined,
                                    combined,
                                    region,
                                    RGN_OR,
                                )


                                _gdi32.DeleteObject(
                                    region
                                )


                    inner = int(
                        round(
                            state["inner"]
                            + 2
                        )
                    )


                    cx = int(
                        round(
                            state["cx"]
                        )
                    )

                    cy = int(
                        round(
                            state["cy"]
                        )
                    )


                    center_region = (
                        _gdi32.CreateEllipticRgn(
                            cx - inner,
                            cy - inner,
                            cx + inner + 1,
                            cy + inner + 1,
                        )
                    )


                    if center_region:

                        _gdi32.CombineRgn(
                            combined,
                            combined,
                            center_region,
                            RGN_OR,
                        )


                        _gdi32.DeleteObject(
                            center_region
                        )


                    result = (
                        _user32.SetWindowRgn(
                            hwnd,
                            combined,
                            True,
                        )
                    )


                    if result == 0:

                        raise RuntimeError(
                            "SetWindowRgn failed."
                        )


                    # Windows owns the region
                    # after SetWindowRgn succeeds.
                    success = True


                finally:

                    if (
                        not success
                        and combined
                    ):

                        _gdi32.DeleteObject(
                            combined
                        )


            # ===============================================================
            # Mouse selection
            # ===============================================================

            def selected_from_cursor():

                if not self._entries:

                    return None


                try:

                    (
                        screen_x,
                        screen_y,
                    ) = _get_cursor_pos()


                except Exception:

                    return None


                dx = (
                    screen_x
                    - state["left"]
                    - state["cx"]
                )


                dy = (
                    screen_y
                    - state["top"]
                    - state["cy"]
                )


                distance = (
                    math.hypot(
                        dx,
                        dy,
                    )
                )


                if (
                    distance
                    <
                    state["inner"]
                    * 0.85
                ):

                    return None


                count = len(
                    self._entries
                )


                if count == 1:

                    return (
                        self._entries[0]
                    )


                step = (
                    math.tau
                    / count
                )


                boundary = (
                    -math.pi / 2.0
                    - step / 2.0
                )


                angle = (
                    math.atan2(
                        dy,
                        dx,
                    )
                )


                index = int(
                    (
                        (
                            angle
                            - boundary
                        )
                        % math.tau
                    )
                    / step
                )


                if (
                    0
                    <= index
                    < count
                ):

                    return (
                        self._entries[
                            index
                        ]
                    )


                return None


            # ===============================================================
            # Drawing
            # ===============================================================

            def redraw(
                selected
            ):

                canvas.delete(
                    "all"
                )


                if not self._entries:

                    return


                count = len(
                    self._entries
                )


                cx = state["cx"]
                cy = state["cy"]

                inner = state["inner"]
                outer = state["outer"]


                step = (
                    math.tau
                    / count
                )


                for (
                    index,
                    entry,
                ) in enumerate(
                    self._entries
                ):

                    (
                        kind,
                        native_id,
                    ) = entry


                    center = (
                        -math.pi / 2.0
                        + (
                            index
                            * step
                        )
                    )


                    a0 = (
                        center
                        - step / 2.0
                        + 0.015
                    )


                    a1 = (
                        center
                        + step / 2.0
                        - 0.015
                    )


                    current = (
                        (
                            kind
                            == "primary"
                        )
                        and
                        (
                            native_id
                            ==
                            self._current_primary
                        )
                    ) or (
                        (
                            kind
                            == "secondary"
                        )
                        and
                        (
                            native_id
                            ==
                            self._current_secondary
                        )
                    )


                    if (
                        entry
                        == selected
                    ):

                        fill = (
                            "#38a8ff"
                        )

                        outline = (
                            "#e8f7ff"
                        )


                    elif current:

                        fill = (
                            "#334a5c"
                        )

                        outline = (
                            "#8dc7e8"
                        )


                    elif (
                        kind
                        == "secondary"
                    ):

                        fill = (
                            "#251d32"
                        )

                        outline = (
                            "#826aa3"
                        )


                    else:

                        fill = (
                            "#17232d"
                        )

                        outline = (
                            "#607483"
                        )


                    points = wedge_points(
                        cx,
                        cy,
                        inner,
                        outer,
                        a0,
                        a1,
                        18,
                    )


                    canvas.create_polygon(
                        flatten(
                            points
                        ),
                        fill=fill,
                        outline=outline,
                        width=2,
                    )


                    label_radius = (
                        (
                            inner
                            + outer
                        )
                        * 0.57
                    )


                    label_x = (
                        cx
                        + label_radius
                        * math.cos(
                            center
                        )
                    )


                    label_y = (
                        cy
                        + label_radius
                        * math.sin(
                            center
                        )
                    )


                    canvas.create_text(
                        label_x,
                        label_y,
                        text=_entry_name(
                            kind,
                            native_id,
                        ),
                        fill="white",
                        font=(
                            "Segoe UI",
                            10,
                            "bold",
                        ),
                        width=105,
                        justify="center",
                    )


                # Center section

                canvas.create_oval(
                    cx - inner,
                    cy - inner,
                    cx + inner,
                    cy + inner,
                    fill="#0b1117",
                    outline="#94a8b5",
                    width=2,
                )


                if selected is None:

                    center_text = (
                        "Move mouse\n"
                        "Release G"
                    )


                else:

                    center_text = (
                        _entry_name(
                            selected[0],
                            selected[1],
                        )
                    )


                canvas.create_text(
                    cx,
                    cy,
                    text=center_text,
                    fill="white",
                    font=(
                        "Segoe UI",
                        12,
                        "bold",
                    ),
                    width=135,
                    justify="center",
                )


            # ===============================================================
            # Show
            # ===============================================================

            def show_overlay(
                entries,
                current_primary,
                current_secondary,
            ):

                (
                    game_left,
                    game_top,
                    game_width,
                    game_height,
                ) = (
                    _find_game_client_rect()
                )


                self._entries = list(
                    entries
                )


                self._current_primary = (
                    current_primary
                )


                self._current_secondary = (
                    current_secondary
                )


                size = (
                    self.OVERLAY_SIZE
                )


                game_cx = (
                    game_left
                    + game_width // 2
                )


                game_cy = (
                    game_top
                    + game_height // 2
                )


                state["left"] = (
                    game_cx
                    - size // 2
                )


                state["top"] = (
                    game_cy
                    - size // 2
                )


                state["cx"] = (
                    size / 2.0
                )


                state["cy"] = (
                    size / 2.0
                )


                state["outer"] = min(
                    270.0,
                    size * 0.43,
                )


                state["inner"] = max(
                    70.0,
                    state["outer"]
                    * 0.29,
                )


                # Only let Tk size the window. Native SetWindowPos below
                # handles the actual desktop coordinates so mixed-DPI and
                # multi-monitor layouts cannot reinterpret the target position.
                root.geometry(
                    f"{size}x{size}"
                )


                canvas.config(
                    width=size,
                    height=size,
                )


                try:

                    self._saved_cursor = (
                        _get_cursor_pos()
                    )


                    _user32.SetCursorPos(
                        int(
                            state["left"]
                            + state["cx"]
                        ),
                        int(
                            state["top"]
                            + state["cy"]
                        ),
                    )


                except Exception:

                    self._saved_cursor = None


                self._set_selected(
                    None
                )


                state["last_selected"] = (
                    object()
                )


                root.deiconify()

                root.update_idletasks()

                # Tk exposes a child/client HWND through winfo_id() on
                # Windows. Moving that child leaves the actual top-level
                # wrapper at its old desktop position (commonly 0,0), which
                # is why v3 appeared in the monitor's top-left corner.
                client_hwnd = root.winfo_id()
                wrapper_hwnd = (
                    _user32.GetParent(client_hwnd)
                    or client_hwnd
                )

                if not _user32.SetWindowPos(
                    wrapper_hwnd,
                    HWND_TOPMOST,
                    int(state["left"]),
                    int(state["top"]),
                    int(size),
                    int(size),
                    SWP_NOACTIVATE
                    | SWP_NOOWNERZORDER,
                ):
                    raise RuntimeError(
                        "SetWindowPos failed while positioning wheel."
                    )

                root.lift()


                apply_clickthrough()

                apply_window_shape()


                state["visible"] = True


                redraw(
                    None
                )


            # ===============================================================
            # Hide
            # ===============================================================

            def hide_overlay():

                if not state["visible"]:

                    return


                state["visible"] = False


                root.withdraw()


                if (
                    self._saved_cursor
                    is not None
                ):

                    try:

                        _user32.SetCursorPos(
                            self._saved_cursor[0],
                            self._saved_cursor[1],
                        )


                    except Exception:

                        pass


                self._saved_cursor = None


            # ===============================================================
            # Overlay loop
            # ===============================================================

            def tick():

                try:

                    while True:

                        command = (
                            self._commands
                            .get_nowait()
                        )


                        if (
                            command[0]
                            == "show"
                        ):

                            show_overlay(
                                command[1],
                                command[2],
                                command[3],
                            )


                        elif (
                            command[0]
                            == "hide"
                        ):

                            hide_overlay()


                except queue.Empty:

                    pass


                except Exception:

                    logger.exception(
                        "[WeaponWheel] "
                        "Overlay command failed."
                    )


                if state["visible"]:

                    selected = (
                        selected_from_cursor()
                    )


                    self._set_selected(
                        selected
                    )


                    if (
                        selected
                        != state[
                            "last_selected"
                        ]
                    ):

                        state[
                            "last_selected"
                        ] = selected


                        redraw(
                            selected
                        )


                root.after(
                    16,
                    tick,
                )


            root.after(
                16,
                tick,
            )


            root.mainloop()


        except Exception:

            logger.exception(
                "[WeaponWheel] "
                "Overlay thread failed."
            )


# ===========================================================================
# pyMHF mod
# ===========================================================================

class WeaponWheelPrototype(Mod):

    def __init__(
        self
    ):

        super().__init__()


        self._request_lock = (
            threading.Lock()
        )


        self._armed_request = None

        self._wheel_open = False

        self._g_down = False


        self._status = (
            "Loading..."
        )


        self._overlay = (
            _WheelOverlay()
        )


        try:

            layout = (
                _resolve_nms_layout()
            )


            self._install_g_takeover()


            self._set_status(
                "READY | signatures resolved | "
                f"global_rva=0x{layout['global_state_ptr_rva']:X} | "
                f"weapon_off=0x{layout['weapon_object_offset']:X} | "
                f"primary_rva=0x{layout['primary_setter_rva']:X} | "
                f"secondary_rva=0x{layout['secondary_setter_rva']:X} | "
                "hold G for radial wheel | "
                "F8 fallback enabled"
            )


        except Exception as exc:

            self._set_status(
                "UNSUPPORTED NMS BUILD | "
                "wheel disabled | "
                f"{exc!r}"
            )


            logger.exception(
                "[WeaponWheel] "
                "NMS layout resolution failed; "
                "G takeover was NOT installed."
            )


    # =======================================================================
    # Status
    # =======================================================================

    @property
    @STRING("Status")
    def status(
        self
    ):

        return (
            self._status
        )


    def _set_status(
        self,
        text,
    ):

        self._status = text


        logger.warning(
            "[WeaponWheel] %s",
            text,
        )


        print(
            f"[WeaponWheel] {text}",
            flush=True,
        )


    # =======================================================================
    # G takeover
    # =======================================================================

    def _install_g_takeover(
        self
    ):

        global _G_BLOCK_HOOK


        # Avoid stacking our own direct G hook
        # after pyMHF reloads.

        if (
            _G_BLOCK_HOOK
            is not None
        ):

            try:

                keyboard.unhook(
                    _G_BLOCK_HOOK
                )


            except Exception:

                pass


            _G_BLOCK_HOOK = None


        _G_BLOCK_HOOK = (
            keyboard.hook_key(
                "g",
                self._on_g_event,
                suppress=True,
            )
        )


    def _on_g_event(
        self,
        event,
    ):

        """
        Blocking keyboard hook behavior:

            True  = allow key through
            False = consume key

        G therefore behaves normally outside NMS.
        While NMS is foreground, both G-down and G-up are swallowed.
        """

        if not _is_nms_foreground():

            return True


        try:

            if (
                event.event_type
                == keyboard.KEY_DOWN
            ):

                if not self._g_down:

                    self._g_down = True


                    self._open_wheel(
                        "G"
                    )


            elif (
                event.event_type
                == keyboard.KEY_UP
            ):

                if self._g_down:

                    self._g_down = False


                    self._close_wheel(
                        "G"
                    )


        except Exception:

            logger.exception(
                "[WeaponWheel] "
                "G takeover callback failed."
            )


        # Prevent vanilla NMS from seeing G.

        return False


    # =======================================================================
    # Wheel lifecycle
    # =======================================================================

    def _open_wheel(
        self,
        source,
    ):

        if self._wheel_open:

            return


        try:

            (
                state,
                entries,
                unknown,
                _values,
            ) = _get_wheel_entries()


            if not entries:

                self._set_status(
                    f"{source} OPEN REFUSED | "
                    "no mapped live entries"
                )

                return


            self._wheel_open = True


            self._overlay.show(
                entries,
                state[
                    "current_mode"
                ],
                state[
                    "secondary_mode"
                ],
            )


            names = ", ".join(
                _entry_name(
                    kind,
                    native_id,
                )
                for (
                    kind,
                    native_id,
                )
                in entries
            )


            message = (
                f"{source} WHEEL OPEN | "
                f"{names}"
            )


            if unknown:

                message += (
                    " | unknown hidden="
                    f"{unknown}"
                )


            self._set_status(
                message
            )


        except Exception as exc:

            self._wheel_open = False


            self._set_status(
                f"{source} "
                "WHEEL OPEN FAILED | "
                f"{exc!r}"
            )


            logger.exception(
                "[WeaponWheel] "
                "Wheel open failed."
            )


    def _close_wheel(
        self,
        source,
    ):

        if not self._wheel_open:

            return


        self._wheel_open = False


        selected = (
            self._overlay
            .selected_entry()
        )


        self._overlay.hide()


        if selected is None:

            self._set_status(
                f"{source} WHEEL CLOSED | "
                "no selection"
            )

            return


        self._arm_entry(
            selected
        )


    # =======================================================================
    # Native request arming
    # =======================================================================

    def _arm_entry(
        self,
        entry,
    ):

        try:

            (
                kind,
                native_id,
            ) = entry


            if kind == "primary":

                if (
                    native_id
                    not in PRIMARY_MODE_NAMES
                ):

                    raise RuntimeError(
                        f"Primary ID "
                        f"{native_id} "
                        "is not mapped."
                    )


            elif kind == "secondary":

                if (
                    native_id
                    not in SECONDARY_MODE_NAMES
                ):

                    raise RuntimeError(
                        f"Secondary ID "
                        f"{native_id} "
                        "is not mapped."
                    )


            else:

                raise RuntimeError(
                    "Unknown entry kind: "
                    f"{kind!r}"
                )


            with self._request_lock:

                if (
                    self._armed_request
                    is not None
                ):

                    self._set_status(
                        "REFUSED | "
                        "request already armed | "
                        f"{self._armed_request!r}"
                    )

                    return


                state = (
                    _read_weapon_state()
                )


                if kind == "primary":

                    if (
                        state["pending_mode"]
                        != state["pending_idle_sentinel"]
                    ):

                        self._set_status(
                            "REFUSED | "
                            "primary request pending | "
                            f"current="
                            f"{state['current_mode']} | "
                            f"pending="
                            f"{state['pending_mode']}"
                        )

                        return


                    if (
                        state["current_mode"]
                        == native_id
                    ):

                        self._set_status(
                            "NO CALL | "
                            f"{_entry_name(kind, native_id)} "
                            "already current"
                        )

                        return


                    _verify_primary_setter(
                        state[
                            "primary_setter_address"
                        ]
                    )


                else:

                    if (
                        state["secondary_mode"]
                        == native_id
                    ):

                        self._set_status(
                            "NO CALL | "
                            f"{_entry_name(kind, native_id)} "
                            "already selected"
                        )

                        return


                    _verify_secondary_setter(
                        state[
                            "secondary_setter_address"
                        ]
                    )


                self._armed_request = (
                    kind,
                    native_id,
                )


            self._set_status(
                "ARMED | "
                f"{kind} | "
                f"{native_id} "
                f"({_entry_name(kind, native_id)})"
            )


        except Exception as exc:

            self._set_status(
                "ARM FAILED | "
                f"{entry!r} | "
                f"{exc!r}"
            )


            logger.exception(
                "[WeaponWheel] "
                "Arm failed."
            )


    # =======================================================================
    # Diagnostics
    # =======================================================================

    @gui_button(
        "Refresh wheel candidates"
    )
    def refresh_wheel_candidates(
        self
    ):

        try:

            (
                state,
                entries,
                unknown,
                _values,
            ) = _get_wheel_entries()


            entry_text = ", ".join(
                (
                    f"{kind}:"
                    f"{native_id}:"
                    f"{_entry_name(kind, native_id)}"
                )
                for (
                    kind,
                    native_id,
                )
                in entries
            )


            if not entry_text:

                entry_text = "none"


            unknown_text = (
                ",".join(
                    str(value)
                    for value in unknown
                )
                if unknown
                else "none"
            )


            self._set_status(
                "WHEEL ENTRIES | "
                f"{entry_text} | "
                f"primary="
                f"{state['current_mode']} | "
                f"secondary="
                f"{state['secondary_mode']} | "
                f"unknown="
                f"{unknown_text} | "
                "filtered=9,10"
            )


        except Exception as exc:

            self._set_status(
                "REFRESH FAILED | "
                f"{exc!r}"
            )


            logger.exception(
                "[WeaponWheel] "
                "Refresh failed."
            )


    @gui_button(
        "Read weapon state"
    )
    def read_weapon_state(
        self
    ):

        try:

            state = (
                _read_weapon_state()
            )


            primary_name = (
                PRIMARY_MODE_NAMES.get(
                    state[
                        "current_mode"
                    ],
                    (
                        "Unknown "
                        f"{state['current_mode']}"
                    ),
                )
            )


            secondary_name = (
                SECONDARY_MODE_NAMES.get(
                    state[
                        "secondary_mode"
                    ],
                    (
                        "Unknown "
                        f"{state['secondary_mode']}"
                    ),
                )
            )


            self._set_status(
                "READ | "
                f"primary="
                f"{state['current_mode']} "
                f"({primary_name}) | "
                f"pending="
                f"{state['pending_mode']} | "
                f"secondary="
                f"{state['secondary_mode']} "
                f"({secondary_name})"
            )


        except Exception as exc:

            self._set_status(
                "READ FAILED | "
                f"{exc!r}"
            )


            logger.exception(
                "[WeaponWheel] "
                "Read failed."
            )


    # =======================================================================
    # F8 fallback
    # =======================================================================

    @on_key_pressed(
        "f8"
    )
    def f8_down(
        self
    ):

        self._open_wheel(
            "F8"
        )


    @on_key_release(
        "f8"
    )
    def f8_up(
        self
    ):

        self._close_wheel(
            "F8"
        )


    # =======================================================================
    # Execute exactly one native call
    # =======================================================================

    @nms.cGcPlayer.Update.before
    def player_update(
        self,
        this,
        lf_step,
    ):

        with self._request_lock:

            request = (
                self._armed_request
            )


            if request is None:

                return


            self._armed_request = None


        (
            kind,
            native_id,
        ) = request


        try:

            state = (
                _read_weapon_state()
            )


            # ===============================================================
            # Primary
            # ===============================================================

            if kind == "primary":

                if (
                    state["pending_mode"]
                    != state["pending_idle_sentinel"]
                ):

                    self._set_status(
                        "ABORTED | "
                        "primary transition pending | "
                        f"wanted={native_id} | "
                        f"current="
                        f"{state['current_mode']} | "
                        f"pending="
                        f"{state['pending_mode']}"
                    )

                    return


                if (
                    state["current_mode"]
                    == native_id
                ):

                    self._set_status(
                        "NO CALL | "
                        f"{_entry_name(kind, native_id)} "
                        "became current "
                        "before execution"
                    )

                    return


                _verify_primary_setter(
                    state[
                        "primary_setter_address"
                    ]
                )


                before = (
                    state[
                        "current_mode"
                    ]
                )


                setter = (
                    _SetWeaponModeProto(
                        state[
                            "primary_setter_address"
                        ]
                    )
                )


                setter(
                    ctypes.c_void_p(
                        state[
                            "weapon_object"
                        ]
                    ),
                    native_id,
                )


                after_state = (
                    _read_weapon_state()
                )


                after = (
                    after_state[
                        "current_mode"
                    ]
                )


                pending = (
                    after_state[
                        "pending_mode"
                    ]
                )


                if (
                    after
                    == native_id
                    and
                    pending
                    == after_state["pending_idle_sentinel"]
                ):

                    result = (
                        "COMMITTED"
                    )


                elif (
                    pending
                    == native_id
                ):

                    result = (
                        "PENDING / DEFERRED"
                    )


                else:

                    result = (
                        "INSPECT STATE"
                    )


                self._set_status(
                    "PRIMARY "
                    f"[{result}] | "
                    f"{_entry_name(kind, native_id)} | "
                    f"before={before} | "
                    f"requested={native_id} | "
                    f"after={after} | "
                    f"pending={pending}"
                )


            # ===============================================================
            # Secondary
            # ===============================================================

            elif kind == "secondary":

                if (
                    state["secondary_mode"]
                    == native_id
                ):

                    self._set_status(
                        "NO CALL | "
                        f"{_entry_name(kind, native_id)} "
                        "became selected "
                        "before execution"
                    )

                    return


                _verify_secondary_setter(
                    state[
                        "secondary_setter_address"
                    ]
                )


                before = (
                    state[
                        "secondary_mode"
                    ]
                )


                setter = (
                    _SetWeaponModeProto(
                        state[
                            "secondary_setter_address"
                        ]
                    )
                )


                setter(
                    ctypes.c_void_p(
                        state[
                            "weapon_object"
                        ]
                    ),
                    native_id,
                )


                after_state = (
                    _read_weapon_state()
                )


                after = (
                    after_state[
                        "secondary_mode"
                    ]
                )


                if (
                    after
                    == native_id
                ):

                    result = (
                        "COMMITTED"
                    )


                else:

                    result = (
                        "INSPECT STATE"
                    )


                self._set_status(
                    "SECONDARY "
                    f"[{result}] | "
                    f"{_entry_name(kind, native_id)} | "
                    f"before={before} | "
                    f"requested={native_id} | "
                    f"after={after}"
                )


        except Exception as exc:

            self._set_status(
                "CALL FAILED | "
                f"{kind}:"
                f"{native_id} "
                f"({_entry_name(kind, native_id)}) | "
                f"{exc!r}"
            )


            logger.exception(
                "[WeaponWheel] "
                "Native call failed."
            )
