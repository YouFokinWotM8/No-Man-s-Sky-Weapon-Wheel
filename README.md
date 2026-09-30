# No Man's Sky Radial Multitool Weapon Wheel

A pyMHF / NMS.py mod that replaces sequential multitool weapon cycling with direct radial selection.

The mod now supports:

- direct primary weapon selection;
- direct secondary/alt-weapon selection;
- automatic detection of installed multitool technologies;
- a hold-and-release radial weapon wheel;
- `G` as the normal wheel key;
- `F8` as a fallback/test binding;
- dynamic runtime signature scanning instead of relying entirely on hard-coded RVAs;
- a smaller, semi-transparent, background-free Win32 radial interface.

---

# Current status

## September 30, 2026

The mod is currently working again after the September 30 No Man's Sky update.

The update changed several native addresses and offsets that the earlier version relied on. The mod was repaired and the address-resolution system was redesigned so that most update-sensitive values are now located dynamically at runtime.

### Confirmed working

- Direct primary weapon selection.
- Direct secondary weapon selection.
- Dynamic installed-mode detection.
- Primary and secondary entries on the same wheel.
- `G` hold/release radial selection.
- `F8` fallback/test selection.
- Exactly one native setter call per wheel selection.
- Native deferred primary transitions are respected.
- The mod does not manually force current/pending weapon state.
- Runtime signature scanning for the important native functions and layout values.
- Runtime validation before native calls.
- Safe failure when the expected NMS code layout cannot be resolved.
- Smaller radial-wheel GUI.
- Semi-transparent wheel rendering.
- Win32-shaped overlay with no rectangular background.
- Wheel positioning near the held multitool area rather than directly in the middle of the screen.

### Current GUI behavior

The current interface uses approximately:

```text
Wheel window size: 450 × 450
Opacity:           78%
Horizontal anchor: 56% of game client width
Vertical anchor:   60% of game client height

The native overlay window is clipped to the actual wedge geometry and center circle using Win32 regions, so the previous rectangular background is gone.
The GUI currently uses:
CreatePolygonRgn
CreateEllipticRgn
CombineRgn
SetWindowRgn

The top-level Tk wrapper is used for positioning and window shaping, while the Tk client HWND retains the click-through / input-related extended styles.
Known UI limitation
Because the wheel is now smaller, it is possible to move the cursor completely outside the shaped overlay while still holding G.
If this happens, No Man's Sky can resume consuming mouse movement for camera control while the wheel is still visible.
A cursor-confinement experiment was tested and intentionally removed because the invisible constrained area felt too restrictive.
The current version therefore leaves mouse movement unrestricted.
Why this mod exists
No Man's Sky normally cycles multitool weapon modes sequentially.
Once a multitool has many technologies installed, repeatedly cycling through every mode becomes slow and easy to overshoot.
The goal of this project was to find the game's real weapon-selection state and native selection functions so that the player can directly choose a desired weapon from a radial menu.
The important design decision is:
Use No Man's Sky's own native weapon-selection functions instead of manually forcing weapon-state fields or simulating a long series of G presses.

This lets the game continue to own its normal transition behavior.
Controls
Hold G
    ↓
Open radial weapon wheel
    ↓
Move mouse toward desired weapon
    ↓
Release G
    ↓
Selected weapon is requested through the game's native setter

Fallback/test binding:
Hold F8
Release F8

F8 uses the same radial selection path without taking over the normal G input.
Installation
The current development setup uses:
- No Man's Sky
- NMS.py / nmspy
- pyMHF
- Python 3.13
Typical pyMHF launch:
pymhf.exe run nmspy

Typical mod layout:
No Man's Sky
└── GAMEDATA
    └── MODS
        └── Weapon
            └── WeaponWheelPrototype.py

Machine-specific usernames and absolute local paths are intentionally omitted.
Current architecture
The mod now has four main pieces:
Input
  ↓
Dynamic weapon-state discovery
  ↓
Radial UI
  ↓
Native primary / secondary setter

More specifically:
                ┌─────────────────────┐
                │ Hold G / F8         │
                └─────────┬───────────┘
                          │
                          v
                ┌─────────────────────┐
                │ Read installed-mode │
                │ table               │
                └─────────┬───────────┘
                          │
                          v
                ┌─────────────────────┐
                │ Filter internal /   │
                │ unmapped modes      │
                └─────────┬───────────┘
                          │
                          v
                ┌─────────────────────┐
                │ Build radial wheel  │
                └─────────┬───────────┘
                          │
                          v
                ┌─────────────────────┐
                │ Mouse selects wedge │
                └─────────┬───────────┘
                          │
                    key released
                          │
              ┌───────────┴────────────┐
              │                        │
              v                        v
     ┌──────────────────┐     ┌──────────────────┐
     │ Primary entry    │     │ Secondary entry  │
     │                  │     │                  │
     │ primary setter   │     │ secondary setter │
     └──────────────────┘     └──────────────────┘

Runtime signature resolution
Older versions of the mod depended on several fixed RVAs.
That became a problem when the September 30 update moved native functions and object data.
The current build instead scans the loaded NMS.exe .text section for instruction signatures and derives important values from the matching instructions.
The current resolver dynamically locates or derives:
- global-state pointer;
- weapon-object offset;
- current-primary offset;
- pending-primary offset;
- selected-secondary offset;
- pending idle sentinel;
- primary setter;
- secondary setter;
- installed-mode table offset.
The important signatures currently include:
GLOBAL_STATE_SIGNATURE
PRIMARY_SETTER_SIGNATURE
SECONDARY_SETTER_SIGNATURE
PENDING_MODE_SIGNATURE
MODE_TABLE_SIGNATURE
WEAPON_WRAPPER_SIGNATURE

Each signature must resolve uniquely.
If a required signature:
- disappears;
- matches multiple locations;
- resolves to implausible data;
- disagrees with another independent signature;
the wheel is disabled instead of blindly calling an unknown native address.
The resulting status looks similar to:
READY | signatures resolved |
global_rva=... |
weapon_off=... |
primary_rva=... |
secondary_rva=... |
hold G for radial wheel |
F8 fallback enabled

If resolution fails:
UNSUPPORTED NMS BUILD | wheel disabled

Current September 30 build
The repaired build was tested against:
NMS.exe hash:
d542309a7aae90d4fd0d273d3006abe789b0a844

For this build, runtime resolution produced:
GLOBAL_STATE_PTR_RVA     = 0x6E89688
WEAPON_OBJECT_OFFSET     = 0x72CAD0

PENDING_PRIMARY_OFFSET   = 0xF6C
CURRENT_PRIMARY_OFFSET   = 0xF74
CURRENT_SECONDARY_OFFSET = 0xF78

PENDING_IDLE_SENTINEL    = 0x15

PRIMARY_SETTER_RVA       = 0x14080F0
SECONDARY_SETTER_RVA     = 0x140D250

MODE_TABLE_OFFSET        = 0x2352D
MODE_TABLE_STRIDE        = 0x10

These values are documented for reverse-engineering/debugging purposes.
The current mod does not depend on these exact RVAs remaining constant across future builds.
Weapon state
Three weapon-object fields have remained especially important:
weapon_object + 0xF6C = pending/requested primary
weapon_object + 0xF74 = current primary
weapon_object + 0xF78 = selected secondary

The pending-primary field uses:
21 / 0x15

as the idle sentinel.
Conceptually:
F74 = current primary weapon
F6C = requested / pending primary weapon
F78 = selected secondary weapon
21  = no pending primary transition

The mod reads these fields but does not manually force them to simulate weapon changes.
Primary weapons
Confirmed primary IDs:
ID	Mode
0	Boltcaster
1	Scatter Blaster
2	Pulse Spitter
3	Blaze Javelin
5	Mining Beam
11	Terrain Manipulator
19	Fishing Rig / Lost Angler's Rig
20	Gravitino Coil / Gravity Gun


21 is not a selectable weapon.
It is the pending-primary idle sentinel.
Secondary weapons
Confirmed secondary IDs:
ID	Secondary weapon
6	Plasma Launcher
7	Geology Cannon
17	Paralysis Mortar


Secondary selection uses a separate native setter from primary weapon selection.
That separation is necessary because NMS stores current primary state and selected alt-weapon state independently.
Installed-mode detection
The game contains a compact per-mode availability table.
The relevant structure is:
global_state + MODE_TABLE_OFFSET + (mode * 0x10)

Current observed table configuration:
MODE_TABLE_OFFSET = 0x2352D
MODE_TABLE_STRIDE = 0x10

The wheel scans modes:
0 .. 20

and only exposes mapped modes that are actually present on the active multitool.
This was validated by physically removing and reinstalling technologies.
Examples:
- Removing Scatter Blaster removed mode 1.
- Removing Boltcaster removed mode 0.
- Reinstalling Boltcaster restored mode 0.
- Removing Pulse Spitter removed mode 2.
- Removing Blaze Javelin removed mode 3.
- Removing Geology Cannon removed mode 7.
Modes 9 and 10
A nearly stripped multitool was tested with almost every removable technology removed.
The remaining nonzero mode-table entries were:
5, 9, 10

5 is Mining Beam.
Modes:
9
10

behave like internal/baseline entries rather than normal player-facing weapons.
The radial wheel filters both.
Mode 10 was also special-cased by the game's availability logic.
Mode 8 has appeared in broader configurations but has not been isolated confidently enough to expose as a normal wheel entry.
Selection safety
Several safety rules are enforced.
Do not manually write weapon-state fields
The mod does not directly write:
+0xF6C
+0xF74
+0xF78

to fake a weapon change.
The native setters are used instead.
One native request per wheel selection
Releasing the wheel produces one request.
That request is removed from the queue before execution so it cannot accidentally become a per-frame native call.
Respect pending primary transitions
If:
F6C != 21

the mod refuses to begin another primary transition.
This allows NMS to finish its own deferred transition first.
Validate setters before calling
Before a native setter is invoked, its resolved address is checked against the expected signature.
If the code at that address no longer matches, the call is refused.
Safe memory reads
Important runtime state is read through ReadProcessMemory.
The mod checks:
- read success;
- requested read size;
- returned byte count;
- pointer plausibility;
- field-value plausibility.
Fail safely after updates
If the resolver cannot confidently identify the required structures or functions, the wheel is disabled rather than guessing.
Why deferred primary state matters
Some NMS weapon changes do not commit immediately.
A request may temporarily appear in:
weapon_object + 0xF6C

before:
weapon_object + 0xF74

changes.
For example, a native request can produce:
current = old mode
pending = requested mode

before the game completes the transition.
That behavior is intentional.
The mod therefore lets No Man's Sky manage the transition instead of directly overwriting the current field.
Radial-wheel rendering
First prototype
The first real radial menu used a fullscreen Tkinter overlay.
Over NMS / DirectX this rendered as a black screen.
Despite the black screen, moving the mouse and releasing the key still selected different weapons correctly.
That confirmed the following systems were already functional:
- radial angle math;
- mouse tracking;
- press/release lifecycle;
- wedge selection;
- dynamic installed-mode detection;
- native weapon dispatch.
Only the rendering approach was wrong.
Original known-good overlay
The fullscreen overlay was replaced with a:
620 × 620

semi-transparent Tkinter window.
This version intentionally left a visible square behind the wheel.
It confirmed:
- rendering;
- wedge highlighting;
- release-to-select;
- primary selection;
- secondary selection.
Current background-free overlay
The current overlay is smaller:
450 × 450

and is positioned near the held multitool rather than centered directly over the player's view.
The window uses:
SetWindowRgn

with the union of:
wedge polygon regions
+
center circular region

so the actual native window exists only where the radial UI is drawn.
There is no rectangular background behind it.
The current overlay also uses:
-alpha = 0.78

for a less intrusive appearance.
Win32 / Tk HWND detail
Tkinter on Windows exposes more than one relevant HWND.
The current working implementation deliberately treats them differently.
Client / child HWND
Obtained through:
root.winfo_id()


This retains the extended window styles used by the working mouse-selection behavior:
WS_EX_TRANSPARENT
WS_EX_TOOLWINDOW
WS_EX_NOACTIVATE

Top-level wrapper HWND
Obtained through:
GetParent(root.winfo_id())


The wrapper is used for:
- SetWindowPos;
- native screen positioning;
- SetWindowRgn;
- removing the rectangular background.
This split matters.
Applying all of the styles to the wrapper caused NMS to continue consuming relative mouse movement, which made the camera move when the wheel opened.
The current arrangement restores normal radial mouse selection while keeping the square background removed.
Taking over G
During development, F8 was used so the radial system could be tested independently of vanilla weapon cycling.
The final control is:
Hold G    -> open wheel
Release G -> request selected weapon

The Python keyboard hook is now confirmed working in-game.
While NMS is the foreground application:
- G down is consumed;
- G up is consumed;
- the radial wheel handles the selection instead.
Outside NMS, the hook is designed to allow G through normally.
F8 remains available as a fallback/test path.
Reverse-engineering history
1. Isolating the weapon project
This began as a separate NMS.py experiment from the terrain/raycast work in the larger project.
SiteCapture was disabled so the weapon work could be tested independently.
Early x64dbg sessions also exposed startup freezes caused by debugger TLS-callback/event pauses, so those break conditions had to be disabled before useful tracing could begin.
Early changing-memory candidates found through general scanning were false leads, so the project moved toward tracing the real input and weapon-cycle paths.
2. Tracing the G key
The first useful input result was:
SetButton RVA: 0x2C23BE0

Pressing G was observed as:
0x67

through a caller/return path around:
0x2C2E3A5

on two input ports.
A generic GetButton candidate at:
0x2C1DDE0

did not receive G during the useful test path.
3. Finding the original primary setter
The original tested build exposed:
Primary setter RVA: 0x13FFB80

Calling convention:
RCX = weapon object / self
EDX = requested primary mode ID

The original weapon object was reached through:
GLOBAL_STATE_PTR_RVA = 0x6E7AAE8
WEAPON_OBJECT_OFFSET = 0x71CA70

Conceptually:
global_state  = *(NMS.exe + GLOBAL_STATE_PTR_RVA)
weapon_object = global_state + WEAPON_OBJECT_OFFSET

These values are now historical.
The current build derives the corresponding values dynamically.
4. Correcting the weapon-state layout
One of the major discoveries was that the existing NMS.py layout was stale for the tested build.
Observed fields:
weapon_object + 0xF74 = current primary mode
weapon_object + 0xF6C = pending/requested primary mode

The pending field uses:
21 / 0x15

as the idle sentinel.
A read-only WeaponStateProbe.py was created first so the values could be verified without modifying memory.
5. Finding the original normal cycle routine
The original tested build contained:
Cycle routine RVA:  0x1404E80
Cycle wrapper RVA:  0x1404E40

The cycle routine starts from the current primary field, advances candidate IDs through the available mode range, checks availability, and eventually invokes the primary setter.
This strongly tied the discovered primary setter to the game's normal weapon-cycle path.
These original RVAs are retained here as reverse-engineering history rather than current constants.
6. A useful failed experiment
A temporary native setter tracer was installed to record calls.
During that capture, vanilla G stopped switching weapons correctly and the setter showed a large repeated-call pattern from an update path.
That trace was considered contaminated.
The hook was removed and the setter bytes were verified restored.
This changed the development strategy:
- prefer read-only probes;
- understand the native ABI before direct calls;
- make one setter call per selection;
- never spam the setter every frame;
- let NMS own deferred transitions.
7. Proving direct primary selection
A safe direct-selector prototype was built.
Selections were armed from the GUI and executed through:
@nms.cGcPlayer.Update.before


This keeps native calls on the game/update side rather than running them directly inside a Tk callback.
Before calling the setter the mod checked:
pending == 21

and validated the setter code.
Confirmed direct selections included:
- Pulse Spitter → Mining Beam
- Fishing Rig
- Scatter Blaster
- Terrain Manipulator
A normal completed transition could look like:
before=2
requested=5
after=5
pending=21

Other requests demonstrated legitimate deferred behavior.
Discovering secondary weapon state
The first radial implementation initially treated a secondary mode like a normal primary weapon.
That caused incorrect selection behavior and revealed that No Man's Sky maintains separate primary and secondary weapon state.
A dedicated read-only A → B → A probe was created.
Example test:
A1 = Plasma Launcher
B  = Paralysis Mortar
A2 = Plasma Launcher

The scanner looked for stable bytes satisfying:
A1 == A2
A1 != B

The meaningful result was:
weapon_object + 0xF78

with:
Plasma Launcher   = 6
Paralysis Mortar = 17

The important weapon fields were therefore:
+0xF6C = pending primary
+0xF74 = current primary
+0xF78 = selected secondary

Finding the original secondary setter
With +0xF78 identified, x64dbg placed a hardware write breakpoint on the live field.
Switching alt weapons normally caused a break in the original build at:
Secondary setter RVA: 0x1404CE0

Calling convention:
RCX = weapon_object
EDX = secondary weapon ID

This was confirmed with:
6  = Plasma Launcher
7  = Geology Cannon
17 = Paralysis Mortar

As with the primary setter, this old RVA is historical.
The current implementation locates the secondary setter dynamically.
September 30 repair
A September 30 game update moved the important global pointer, weapon-object offset, and native setter functions.
The original hard-coded build stopped working.
The repaired build was validated with:
Exe hash:
d542309a7aae90d4fd0d273d3006abe789b0a844

Reverse engineering located the new equivalents:
global state RVA:    0x6E89688
weapon object offset:0x72CAD0

primary setter RVA:  0x14080F0
secondary setter RVA:0x140D250

The known weapon fields remained:
+0xF6C
+0xF74
+0xF78

The installed-mode table remained:
+0x2352D
stride 0x10

Rather than simply hard-code these new addresses, the mod was redesigned around runtime signature scanning.
That is the current architecture.
Historical original build
One earlier working build reported:
Exe hash:
f22d4dde3eafddfd567915657aa7491eebee2012

Original values included:
GLOBAL_STATE_PTR_RVA = 0x6E7AAE8
WEAPON_OBJECT_OFFSET = 0x71CA70

Primary setter RVA   = 0x13FFB80
Secondary setter RVA = 0x1404CE0

Cycle wrapper RVA    = 0x1404E40
Cycle routine RVA    = 0x1404E80

These should not be treated as current constants.
They are retained as reverse-engineering history.
Why direct selection is better than faking repeated G presses
Simulating repeated G presses would still:
- depend on the currently selected weapon;
- overshoot easily;
- become slower as more technologies are installed;
- make primary/secondary handling awkward;
- rely heavily on timing.
The native approach lets the wheel represent real weapon targets.
The game can go directly from one installed primary weapon to another, or directly change the selected secondary weapon, without traversing every intermediate mode.
Tools used
Development has used:
- No Man's Sky
- NMS.py / nmspy
- pyMHF
- Python 3.13
- Ghidra
- x64dbg
- Python ctypes
- Tkinter
- Win32 APIs
- ReadProcessMemory
- read-only diagnostic/probe mods
- temporary native hooks for tracing
- hardware write breakpoints
What did not work
Several failed experiments were still useful.
- Early memory candidates were false positives.
- Searching obvious weapon names did not expose a simple exported selector.
- The generic GetButton candidate did not expose G through the useful path.
- Intrusive setter tracing contaminated normal weapon behavior.
- Fullscreen Tk transparent/color-key rendering produced a black screen over NMS.
- Treating secondary weapons as normal primary modes selected the wrong weapon.
- Shaping only the Tk client HWND left the translucent top-level wrapper visible as a rectangle.
- Applying input/window styles to the wrong HWND caused NMS to retain mouse capture.
- Constraining the cursor with ClipCursor prevented accidental mouse escape but made the usable area feel too restrictive.
Current known limitations
Mouse can leave the smaller wheel
The current radial UI is intentionally compact.
If the cursor is moved completely outside the shaped Win32 wheel, the game can regain normal camera mouse input while G remains held.
The wheel itself remains visible.
A future input revision may address this without physically trapping the pointer.
Signature scanning is more update-resistant, not update-proof
The current build no longer depends exclusively on exact hard-coded RVAs.
However, a major Hello Games update can still change:
- function instruction patterns;
- structure layout;
- field offsets;
- calling conventions;
- weapon-mode logic.
If that happens, the relevant signatures or validation rules will need to be updated.
The goal is graceful failure rather than assuming every future executable will remain compatible.
Next steps
Possible future work:
1. Improve mouse ownership while the wheel is open without using a restrictive cursor bounding box.
2. Add user configuration.
3. Add optional weapon icons.
4. Improve primary/secondary visual distinction.
5. Re-scan cleanly when the active multitool changes if needed.
6. Improve packaging and installation documentation.
7. Continue strengthening runtime validation.
8. Map any remaining useful unknown mode IDs.
9. Investigate a more native-feeling NMS-style radial UI.
Development takeaway
The biggest lesson was that No Man's Sky multitool selection is not controlled by one simple weapon-number variable.
There are at least three important pieces of state:
current primary
pending primary transition
selected secondary

and two separate native setter functions are needed for correct direct selection.
The working solution came from combining:
- input tracing;
- static disassembly;
- live native-call observation;
- read-only memory probes;
- install/uninstall experiments;
- A/B/A state comparison;
- hardware write breakpoints;
- runtime signature scanning;
- Win32 window manipulation;
- and repeated in-game validation.
The result is a radial selector that no longer needs to fake repeated weapon-cycle presses and no longer depends entirely on fixed native addresses.
It can address No Man's Sky's actual weapon-selection machinery directly while failing safely when the expected native layout cannot be verified.

The main change I’d strongly keep is replacing the old top claim that it “should now keep functioning after Hello Games updates the game.” The new scanner makes it much more update-resistant, but a sufficiently large code change can still invalidate the signatures, so the README now describes that accurately rather than promising permanent compatibility.
