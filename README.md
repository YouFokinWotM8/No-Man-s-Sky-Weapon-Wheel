<div align="center">

# No Man's Sky Radial Multitool Weapon Wheel

### Direct radial selection for No Man's Sky multitool weapons using pyMHF / NMS.py

Hold **G**, move toward the weapon you want, then release **G** to select it.

</div>

---

> [!NOTE]
> **Status — September 30, 2026**
>
> The mod is working again after the September 30 No Man's Sky update.
>
> The latest repair also replaces most hard-coded, update-sensitive addresses with runtime signature scanning and validation. This makes the mod substantially more update-resistant, but not completely update-proof.

## Features

- Direct selection of primary multitool weapon modes.
- Direct selection of secondary / alt weapons.
- One radial wheel for both primary and secondary weapons.
- Automatically detects which supported modes are installed on the active multitool.
- Hold **G** to open the wheel and release **G** to select.
- **F8** remains available as a fallback/test binding.
- Uses No Man's Sky's own native weapon-selection functions.
- Respects the game's deferred primary-weapon transition behavior.
- Makes exactly one native setter request per wheel selection.
- Does **not** manually force current/pending weapon-state fields.
- Dynamically resolves important native functions and offsets at runtime.
- Validates resolved code before making native calls.
- Fails safely when the expected NMS layout cannot be verified.
- Compact, semi-transparent radial interface.
- Background-free Win32-shaped overlay.
- Wheel is positioned near the held multitool area instead of directly over the center of the screen.

---

## Table of contents

- [Controls](#controls)
- [Installation](#installation)
- [Current status](#current-status)
- [Current GUI](#current-gui)
- [Known limitation](#known-limitation)
- [Why this mod exists](#why-this-mod-exists)
- [How it works](#how-it-works)
- [Runtime signature resolution](#runtime-signature-resolution)
- [Current September 30 build](#current-september-30-build)
- [Weapon state](#weapon-state)
- [Primary weapon IDs](#primary-weapon-ids)
- [Secondary weapon IDs](#secondary-weapon-ids)
- [Installed-mode detection](#installed-mode-detection)
- [Modes 9 and 10](#modes-9-and-10)
- [Selection safety](#selection-safety)
- [Radial-wheel rendering](#radial-wheel-rendering)
- [Win32 / Tkinter HWND details](#win32--tkinter-hwnd-details)
- [Reverse-engineering history](#reverse-engineering-history)
- [September 30 repair](#september-30-repair)
- [Historical build information](#historical-build-information)
- [What did not work](#what-did-not-work)
- [Tools used](#tools-used)
- [Why direct selection is better than repeated G presses](#why-direct-selection-is-better-than-repeated-g-presses)
- [Future work](#future-work)
- [Development takeaway](#development-takeaway)

---

# Controls

| Action | Control |
|---|---|
| Open radial wheel | Hold `G` |
| Highlight a weapon | Move the mouse toward a wedge |
| Select highlighted weapon | Release `G` |
| Fallback/test wheel | Hold/release `F8` |

Normal flow:

```text
Hold G
  ↓
Open radial wheel
  ↓
Move mouse toward desired weapon
  ↓
Release G
  ↓
Queue exactly one native weapon-selection request
```

`F8` uses the same radial-selection system without relying on the normal `G` takeover path.

---

# Installation

The current development setup uses:

- No Man's Sky
- NMS.py / nmspy
- pyMHF
- Python 3.13

Typical pyMHF launch:

```bat
pymhf.exe run nmspy
```

Typical mod layout:

```text
No Man's Sky
└── GAMEDATA
    └── MODS
        └── Weapon
            └── WeaponWheelPrototype.py
```

Machine-specific usernames and local absolute paths are intentionally omitted.

---

# Current status

## Confirmed working

The following have been confirmed in-game:

- Direct primary weapon selection.
- Direct secondary weapon selection.
- Dynamic installed-mode detection.
- Primary and secondary entries on the same radial wheel.
- Plasma Launcher, Geology Cannon, and Paralysis Mortar selection.
- `G` hold/release radial control.
- `F8` fallback/test control.
- One native setter request per wheel selection.
- Deferred primary transitions owned by NMS rather than forced by the mod.
- Runtime signature scanning.
- Runtime address/layout validation.
- Safe failure when signatures cannot be resolved.
- Smaller radial-wheel interface.
- Semi-transparent rendering.
- Correct placement near the held multitool area.
- Background-free shaped Win32 window.
- Mouse selection restored after separating the Tk client HWND behavior from the top-level wrapper HWND behavior.

> [!IMPORTANT]
> The current mod no longer depends entirely on the exact RVAs from the original reverse-engineering build.
>
> Those old values are still documented below because they are useful development history, but the current implementation dynamically locates the important functions and layout values.

---

# Current GUI

The current wheel is intentionally smaller and less intrusive than the original prototype.

Current presentation:

```text
Wheel window size: 450 × 450
Opacity:           78%
Horizontal anchor: 56% of game client width
Vertical anchor:   60% of game client height
```

The wheel is positioned slightly right and below the screen center so that, at the tested 120° FOV, it appears in open space near the held multitool rather than directly over the player or reticle.

The wheel uses a shaped native Win32 region instead of a normal rectangular overlay.

The relevant APIs are:

```text
CreatePolygonRgn
CreateEllipticRgn
CombineRgn
SetWindowRgn
```

The resulting native window exists only where the wedges and center circle are drawn.

That removes the large rectangular background that earlier Tkinter prototypes displayed behind the interface.

---

# Known limitation

Because the current wheel is compact, the mouse can be moved completely outside the shaped overlay while `G` is still held.

When that happens, No Man's Sky can resume consuming mouse movement as normal camera input even though the wheel is still visible.

A `ClipCursor` experiment was tested to trap the mouse inside an invisible selection area, but it was intentionally removed because the constrained area felt too restrictive.

The current version therefore leaves pointer movement unrestricted.

A future input revision may address this without physically trapping the mouse.

---

# Why this mod exists

No Man's Sky normally cycles multitool weapon modes sequentially.

With many technologies installed, repeatedly cycling through every mode becomes slow and easy to overshoot.

The goal of this project was to identify the real weapon state and native selection functions, determine which modes are installed on the active multitool, and expose those targets through a radial menu.

The central design decision is:

> **Use No Man's Sky's own native weapon-selection functions instead of forcing state fields or simulating repeated `G` presses.**

This lets NMS continue to own its normal transition logic.

---

# How it works

At a high level:

```text
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
```

Primary and secondary weapons use separate native setters because NMS keeps those selections in separate state.

---

# Runtime signature resolution

Older builds of this mod relied on fixed RVAs.

That broke when the September 30 update moved several functions and data structures.

The current implementation scans the loaded `NMS.exe` `.text` section for instruction signatures and derives update-sensitive values from the matching instructions.

The resolver dynamically locates or derives:

- global-state pointer;
- weapon-object offset;
- current-primary field offset;
- pending-primary field offset;
- selected-secondary field offset;
- pending idle sentinel;
- primary setter;
- secondary setter;
- installed-mode table offset.

Current signature groups include:

```text
GLOBAL_STATE_SIGNATURE
PRIMARY_SETTER_SIGNATURE
SECONDARY_SETTER_SIGNATURE
PENDING_MODE_SIGNATURE
MODE_TABLE_SIGNATURE
WEAPON_WRAPPER_SIGNATURE
```

Each required signature is expected to resolve uniquely.

The resolver also cross-checks independently derived values where possible.

If a required signature:

- does not match;
- matches more than one location;
- resolves to implausible values;
- disagrees with another independent signature;
- or no longer matches immediately before a native call;

the wheel refuses to make the native call.

A successful startup reports values similar to:

```text
READY | signatures resolved |
global_rva=... |
weapon_off=... |
primary_rva=... |
secondary_rva=... |
hold G for radial wheel |
F8 fallback enabled
```

If the native layout cannot be verified:

```text
UNSUPPORTED NMS BUILD | wheel disabled
```

> [!NOTE]
> Signature scanning makes the mod more resilient to ordinary address movement, but a sufficiently large game update can still change the actual code patterns, structure layout, calling conventions, or weapon logic.

---

# Current September 30 build

The repaired build was tested against:

```text
NMS.exe hash:
d542309a7aae90d4fd0d273d3006abe789b0a844
```

For that build, the runtime resolver found:

```text
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
```

These values are useful for reverse-engineering and diagnostics.

The current mod does **not** assume those exact RVAs will remain unchanged in future game builds.

---

# Weapon state

Three weapon-object fields are especially important:

```text
weapon_object + 0xF6C = pending/requested primary
weapon_object + 0xF74 = current primary
weapon_object + 0xF78 = selected secondary
```

The pending-primary field uses:

```text
21 / 0x15
```

as the idle sentinel.

Conceptually:

```text
F74 = current primary weapon
F6C = requested / pending primary weapon
F78 = selected secondary weapon
21  = no pending primary transition
```

The mod reads these fields but does not manually force them to simulate a weapon change.

---

# Primary weapon IDs

Confirmed primary IDs:

| ID | Mode |
|---:|---|
| `0` | Boltcaster |
| `1` | Scatter Blaster |
| `2` | Pulse Spitter |
| `3` | Blaze Javelin |
| `5` | Mining Beam |
| `11` | Terrain Manipulator |
| `19` | Fishing Rig / Lost Angler's Rig |
| `20` | Gravitino Coil / Gravity Gun |

`21` is **not** a selectable weapon.

It is the pending-primary idle sentinel.

---

# Secondary weapon IDs

Confirmed secondary IDs:

| ID | Secondary weapon |
|---:|---|
| `6` | Plasma Launcher |
| `7` | Geology Cannon |
| `17` | Paralysis Mortar |

Secondary selection uses a different native setter from primary selection.

This distinction was necessary because NMS maintains current primary state and selected secondary state independently.

---

# Installed-mode detection

Hard-coding every possible weapon would be wrong because different multitools have different technologies installed.

Static analysis exposed a compact per-mode availability table:

```text
global_state + MODE_TABLE_OFFSET + (mode * 0x10)
```

Current observed configuration:

```text
MODE_TABLE_OFFSET = 0x2352D
MODE_TABLE_STRIDE = 0x10
```

The wheel scans mode IDs:

```text
0 .. 20
```

and only exposes mapped modes that are actually present.

## Install/remove validation

The table was validated by physically removing and reinstalling technologies.

Examples:

- Removing Scatter Blaster removed mode `1`.
- Removing Boltcaster removed mode `0`.
- Reinstalling Boltcaster restored mode `0`.
- Removing Pulse Spitter removed mode `2`.
- Removing Blaze Javelin removed mode `3`.
- Removing Geology Cannon removed mode `7`.

This confirmed that the table is useful for dynamically deciding which entries should appear in the radial menu.

---

# Modes 9 and 10

A nearly stripped multitool was tested with almost every removable technology removed.

The remaining nonzero table entries were:

```text
5, 9, 10
```

`5` is Mining Beam.

Modes:

```text
9
10
```

behave like internal/baseline entries rather than normal player-facing weapon choices.

The wheel filters both.

Mode `10` was also special-cased by the game's availability logic.

Mode `8` has appeared in broader configurations but has not been isolated confidently enough to expose as a normal wheel entry.

---

# Selection safety

The current design follows several safety rules learned during reverse engineering.

## Do not manually force weapon-state fields

The mod does not directly write:

```text
+0xF6C
+0xF74
+0xF78
```

to fake a state change.

The game's native setters are used instead.

## One request per selection

Wheel release creates one selection request.

That request is removed from the queue before execution so it cannot accidentally turn into a native call every frame.

## Respect pending primary transitions

If:

```text
F6C != 21
```

the mod refuses to begin another primary transition.

This gives NMS time to finish its own deferred transition.

## Validate native code before calling it

Before either setter is invoked, the resolved native address is checked against the expected signature.

If the code no longer matches, the call is refused.

## Safe memory reads

Important runtime state is read through `ReadProcessMemory`.

The mod checks:

- read success;
- requested read size;
- returned byte count;
- pointer plausibility;
- resolved field plausibility.

## Fail safely after game updates

If the resolver cannot confidently identify the required structures or functions, the wheel is disabled instead of guessing.

---

# Deferred primary transitions

Some NMS weapon changes do not commit immediately.

A request can temporarily appear in:

```text
weapon_object + 0xF6C
```

before:

```text
weapon_object + 0xF74
```

changes.

A transition can therefore temporarily look like:

```text
current = old mode
pending = requested mode
```

before the game finishes the change.

That behavior is intentional.

The mod lets No Man's Sky complete the transition instead of directly overwriting `F74` or `F6C`.

---

# Radial-wheel rendering

## First prototype: fullscreen overlay

The first real radial implementation used a fullscreen Tkinter overlay.

Over No Man's Sky / DirectX it rendered as a black screen.

However, moving the mouse around that black screen and releasing the wheel key still selected different weapons correctly.

That proved these systems were already working:

- radial-angle math;
- mouse tracking;
- press/release lifecycle;
- wedge selection;
- dynamic installed-mode detection;
- native weapon dispatch.

Only the rendering method was wrong.

## Second prototype: visible rectangular window

The fullscreen overlay was replaced with a centered:

```text
620 × 620
```

semi-transparent Tkinter window.

That version intentionally left a visible square behind the wheel, but it confirmed:

- wheel rendering;
- wedge highlighting;
- release-to-select behavior;
- primary selection;
- secondary selection.

## Current prototype: shaped native window

The current wheel uses:

```text
450 × 450
```

and approximately:

```text
78% opacity
```

The top-level window is clipped to the union of the wedge polygons and center circle.

This removes the rectangular background entirely.

---

# Win32 / Tkinter HWND details

Tkinter on Windows exposes more than one relevant HWND.

The current working implementation intentionally treats them differently.

## Tk client / child HWND

Obtained through:

```python
root.winfo_id()
```

The working input-related extended styles remain on this HWND:

```text
WS_EX_TRANSPARENT
WS_EX_TOOLWINDOW
WS_EX_NOACTIVATE
```

## Top-level wrapper HWND

Obtained through:

```python
GetParent(root.winfo_id())
```

The wrapper is used for:

- `SetWindowPos`;
- correct desktop positioning;
- `SetWindowRgn`;
- removing the rectangular background.

This split matters.

Moving or shaping only the child HWND does not correctly control the actual top-level Tk window.

On the other hand, putting the wrong input-related styles onto the top-level wrapper caused No Man's Sky to keep consuming mouse movement, which made the player camera move instead of allowing normal wheel selection.

The current arrangement preserves both:

- correct wheel selection;
- no rectangular background.

---

# Reverse-engineering history

## 1. Isolating the weapon project

This began as a separate NMS.py experiment from the terrain/raycast work in the larger project.

SiteCapture was disabled so weapon work could be tested independently.

Early x64dbg sessions also exposed startup freezes caused by debugger TLS-callback/event pauses, so those break conditions had to be disabled before useful live tracing could begin.

Early changing-memory candidates found through general scanning were false leads, so the project moved toward tracing the actual input and weapon-cycle paths.

---

## 2. Tracing the G key

The first useful input result was:

```text
SetButton RVA: 0x2C23BE0
```

Pressing `G` was observed as:

```text
0x67
```

through a caller/return path around:

```text
0x2C2E3A5
```

on two input ports.

A generic `GetButton` candidate at:

```text
0x2C1DDE0
```

did not receive `G` during the useful test path.

---

## 3. Finding the original primary setter

The original tested build exposed:

```text
Primary setter RVA: 0x13FFB80
```

Working calling convention:

```text
RCX = weapon object / self
EDX = requested primary mode ID
```

The original weapon object was reached through:

```text
GLOBAL_STATE_PTR_RVA = 0x6E7AAE8
WEAPON_OBJECT_OFFSET = 0x71CA70
```

Conceptually:

```text
global_state  = *(NMS.exe + GLOBAL_STATE_PTR_RVA)
weapon_object = global_state + WEAPON_OBJECT_OFFSET
```

These values are now historical.

The current build derives the corresponding values dynamically.

---

## 4. Correcting the weapon-state layout

One of the biggest discoveries was that the existing NMS.py layout was stale for the tested build.

Observed fields:

```text
weapon_object + 0xF74 = current primary mode
weapon_object + 0xF6C = pending/requested primary mode
```

The pending field uses:

```text
21 / 0x15
```

as the idle sentinel.

A read-only `WeaponStateProbe.py` was created first so these values could be verified without modifying memory.

---

## 5. Finding the original cycle routine

Static analysis identified:

```text
Cycle routine RVA:  0x1404E80
Cycle wrapper RVA:  0x1404E40
```

The routine starts from the current primary field, advances candidate IDs through the available mode range, checks availability, and ultimately calls the primary setter.

A natural setter call was observed from around:

```text
0x1404F4B
```

with return around:

```text
0x1404F50
```

This strongly tied the primary setter to the game's normal weapon-cycle path.

These original RVAs are retained as reverse-engineering history rather than current constants.

---

## 6. A useful failed experiment

A temporary native setter tracer was installed to record calls.

During that capture, vanilla `G` stopped switching weapons correctly and the setter showed a large repeated-call pattern from an update path.

That capture was considered contaminated.

The hook was removed and the setter bytes were verified restored.

That changed the development strategy:

- prefer read-only probes;
- understand the ABI before direct calls;
- make one setter call per selection;
- never spam the setter every frame;
- let NMS own deferred transitions.

---

## 7. Proving direct primary selection

A safe direct-selector prototype was built.

Selections were armed from the GUI and executed through:

```python
@nms.cGcPlayer.Update.before
```

This keeps the native call on the game/update side instead of invoking it directly inside a Tk callback.

Before calling the setter, the mod checked:

```text
pending == 21
```

and validated the setter entry bytes.

Confirmed direct selections included:

- Pulse Spitter → Mining Beam
- Fishing Rig
- Scatter Blaster
- Terrain Manipulator

A clean completed transition could look like:

```text
before=2
requested=5
after=5
pending=21
```

Pulse Spitter also demonstrated that some native requests are legitimately deferred.

That is why the mod does not manually write `F74` or `F6C`.

---

## 8. Discovering secondary weapon state

The first radial implementation initially treated ID `6` like a normal primary mode.

That caused the entry labeled as one secondary weapon to bring out another secondary weapon.

This revealed that NMS has separate state for primary weapon mode and secondary / alt-weapon selection.

A dedicated read-only **A → B → A** memory probe was created.

Example test sequence:

```text
A1 = Plasma Launcher
B  = Paralysis Mortar
A2 = Plasma Launcher
```

The probe looked for stable values satisfying:

```text
A1 == A2
A1 != B
```

The meaningful result was:

```text
weapon_object + 0xF78
```

with:

```text
Plasma Launcher   = 6
Paralysis Mortar = 17
```

The important weapon-object fields were therefore:

```text
+0xF6C = pending primary
+0xF74 = current primary
+0xF78 = selected secondary
```

---

## 9. Finding the original secondary setter

With `+0xF78` known, x64dbg placed a hardware write breakpoint on the live secondary field.

Switching the alt weapon normally caused x64dbg to break in:

```text
Secondary setter RVA: 0x1404CE0
```

Calling convention:

```text
RCX = weapon_object
EDX = secondary weapon ID
```

Confirmed IDs:

```text
6  = Plasma Launcher
7  = Geology Cannon
17 = Paralysis Mortar
```

Geology Cannon was validated in-game by installing it, refreshing the wheel state, and selecting it successfully from the radial menu.

As with the primary setter, the old secondary RVA is now historical.

The current implementation locates the setter dynamically.

---

# September 30 repair

The September 30 No Man's Sky update moved several of the addresses used by the original build.

The older fixed-RVA version stopped working.

The repaired executable hash was:

```text
d542309a7aae90d4fd0d273d3006abe789b0a844
```

Reverse engineering located the updated equivalents:

```text
Global state RVA:     0x6E89688
Weapon object offset: 0x72CAD0

Primary setter RVA:   0x14080F0
Secondary setter RVA: 0x140D250
```

The known weapon fields remained:

```text
+0xF6C
+0xF74
+0xF78
```

The installed-mode table remained:

```text
+0x2352D
stride 0x10
```

Instead of simply replacing the old hard-coded constants with new hard-coded constants, the mod was redesigned around runtime signature scanning.

That is the current architecture.

---

# Historical build information

An earlier working build reported:

```text
Exe hash:
f22d4dde3eafddfd567915657aa7491eebee2012
```

Original fixed values included:

```text
GLOBAL_STATE_PTR_RVA = 0x6E7AAE8
WEAPON_OBJECT_OFFSET = 0x71CA70

Primary setter RVA   = 0x13FFB80
Secondary setter RVA = 0x1404CE0

Cycle wrapper RVA    = 0x1404E40
Cycle routine RVA    = 0x1404E80

SetButton RVA        = 0x2C23BE0
Generic GetButton RVA= 0x2C1DDE0
```

These should **not** be treated as current constants.

They are preserved only as reverse-engineering history.

---

# What did not work

Several failed approaches still helped narrow the problem.

- Early memory candidates were false positives.
- Searching obvious weapon names did not expose a convenient exported selector.
- The generic `GetButton` candidate did not expose `G` through the useful path.
- Intrusive setter instrumentation changed normal `G` behavior and contaminated that capture.
- Fullscreen Tk transparent/color-key rendering blacked out the game.
- Treating secondary weapons as ordinary primary modes produced incorrect selections.
- Shaping only the Tk child/client HWND left the top-level translucent rectangle visible.
- Applying input/window styles to the wrong HWND caused NMS to keep consuming mouse movement.
- `ClipCursor` successfully kept the mouse inside a bounded area, but the invisible constraint felt too restrictive and was removed.

---

# Tools used

Development has used:

- No Man's Sky
- NMS.py / nmspy
- pyMHF
- Python 3.13
- Ghidra
- x64dbg
- Python `ctypes`
- Tkinter
- Win32 APIs
- `ReadProcessMemory`
- read-only diagnostic/probe mods
- temporary native hooks for tracing
- hardware write breakpoints
- install/uninstall experiments
- repeated in-game validation

---

# Why direct selection is better than repeated G presses

Simulating repeated `G` presses would still:

- depend on the currently selected weapon;
- overshoot easily;
- take longer as more technologies are installed;
- make primary/secondary handling awkward;
- rely heavily on timing.

The native approach lets the radial wheel represent actual weapon targets.

The game can go directly from Mining Beam to Scatter Blaster, or directly change the selected secondary weapon from Plasma Launcher to Paralysis Mortar, without cycling through every intermediate technology.

---

# Future work

Potential next steps:

1. Improve mouse ownership while the wheel is open without using a restrictive cursor bounding box.
2. Add user configuration.
3. Add optional weapon icons.
4. Improve primary/secondary visual distinction.
5. Improve packaging and installation documentation.
6. Continue strengthening update/version validation.
7. Re-scan cleanly when the active multitool changes if needed.
8. Map any remaining useful unknown mode IDs.
9. Investigate a more native-feeling No Man's Sky-style radial UI.

---

# Development takeaway

The biggest lesson was that No Man's Sky multitool selection is not controlled by one simple weapon-number variable.

There are at least three important pieces of state:

```text
current primary
pending primary transition
selected secondary
```

and two separate native setters are required for correct direct selection.

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

It can address No Man's Sky's real weapon-selection machinery directly while failing safely when the expected native layout cannot be verified.

---

<div align="center">

### No repeated weapon cycling. Pick the weapon you want directly.

</div>
