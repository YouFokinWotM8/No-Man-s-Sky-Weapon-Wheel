# No Man's Sky Radial Multitool Weapon Wheel

~THE RECENT 1.8GB UPDATE ON SEPT 30 HAS BROKEN THE MOD. I WILL BE WORKING ON FIXING IT, AS WELL AS MAKING IT A BIT MORE FUTURE PROOF.~

MOD HAS BEEN UPDATED WITH NEW GUI SIZING, AS WELL AS FUTURE PROOFING. THIS SHOULD NOW KEEP FUNCTIONING AFTER HELLO GAMES UPDATES THE GAME.

> Reverse-engineering notes and development history for a pyMHF / NMS.py mod that replaces tedious multitool weapon cycling with direct radial selection.

## Project status

As of **September 29, 2026**, the core weapon-selection system is working.

Confirmed working:

- Direct selection of primary multitool modes without cycling through every installed weapon.
- Direct selection of secondary/alt weapons through a separate native setter.
- Dynamic detection of installed/available multitool modes.
- A radial wheel prototype that opens while a key is held, highlights a wedge from mouse direction, and performs one native selection when the key is released.
- Primary and secondary weapon selection from the same wheel.
- Plasma Launcher, Geology Cannon, and Paralysis Mortar can all be selected independently through the wheel.
- The game is allowed to own its normal deferred weapon-transition behavior instead of the mod manually forcing state fields.

Still being refined:

- Final transparent/polished wheel rendering.
- `G` now works as the radial-wheel hold/release key, with `F8` retained as a fallback/test binding.
- External-app behavior for `G` should still be treated as something to verify separately.
- Final packaging/configuration and cleanup.

The wheel has now been **user-confirmed with both `G` and `F8`**. `G` works as the intended radial-wheel control while `F8` remains available as a fallback/test binding. The shaped Win32 window revision for removing the rectangular background should still be treated separately unless explicitly re-tested.

---

## Why this mod exists

No Man's Sky normally cycles multitool weapon modes sequentially. Once a multitool has a large number of technologies installed, repeatedly cycling through every mode becomes slow and easy to overshoot.

The goal was to find the actual native weapon state and selection functions, detect which modes are installed on the active multitool, call the game's own selection functions once for the desired target, and expose those targets through a radial menu.

The key design decision was to **use NMS's own native transition functions** rather than continuously forcing state values or simulating a long series of G presses.

---

## Tools used

Development used:

- No Man's Sky
- NMS.py / nmspy
- pyMHF
- Python 3.13
- Ghidra
- x64dbg
- Python `ctypes`
- read-only diagnostic/probe mods
- temporary native hooks for tracing
- Win32 APIs
- Tkinter for the first radial UI prototypes

Typical launch:

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

# Reverse-engineering history

## 1. Isolating the weapon project

This began as a separate NMS.py experiment from the terrain/raycast work in the larger project.

SiteCapture was disabled so the weapon work could be tested in isolation. Early x64dbg sessions also exposed startup freezes caused by debugger TLS-callback/event pauses, so those break conditions had to be disabled before useful live tracing could begin.

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

did **not** receive G during the test, so it was not useful as the consumer we needed.

---

## 3. Finding the primary weapon-mode setter

Static and live tracing eventually identified:

```text
Primary setter RVA: 0x13FFB80
```

Working calling convention:

```text
RCX = weapon object / self
EDX = requested mode ID
```

The weapon object is reached through:

```text
GLOBAL_STATE_PTR_RVA = 0x6E7AAE8
WEAPON_OBJECT_OFFSET = 0x71CA70
```

Conceptually:

```text
global_state = *(NMS.exe + 0x6E7AAE8)
weapon_object = global_state + 0x71CA70
```

A safety check was added so the mod refuses a direct call if the setter no longer begins with the expected bytes:

```text
48 89 5C 24 20
57
48 83 EC 60
48 63 DA
48 8B F9
```

---

## 4. Correcting the weapon-state layout

One of the biggest discoveries was that the current NMS.py layout was stale for this build.

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

So:

```text
F74 = current
F6C = pending
21  = no pending transition
```

A read-only `WeaponStateProbe.py` was created first so these values could be verified without modifying memory.

---

## 5. Finding the normal cycle routine

Static analysis identified:

```text
Cycle routine RVA:     0x1404E80
Cycle gate/wrapper:    0x1404E40
```

The cycle routine starts from `weapon_object + 0xF74`, advances candidate IDs through a 21-entry range, checks availability, and calls the primary setter.

A natural setter call was observed from around:

```text
0x1404F4B
```

with return around:

```text
0x1404F50
```

This strongly tied `0x13FFB80` to the game's real weapon-cycle path.

---

## 6. A useful failed experiment

A temporary native setter tracer was installed to record calls.

During that capture, vanilla `G` stopped switching weapons correctly and the setter showed a large repeated-call pattern from an update path. That capture was considered **contaminated**.

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

Selections were armed from the GUI and executed from:

```python
@nms.cGcPlayer.Update.before
```

This kept the native call on the game/update side rather than directly in the GUI callback.

Before calling the setter the mod checked:

```text
pending == 21
```

and validated the setter entry bytes.

Confirmed direct selections included:

- Pulse Spitter → Mining Beam
- Fishing Rig
- Scatter Blaster
- Terrain Manipulator

A typical clean transition looked like:

```text
before=2
requested=5
after=5
pending=21
```

Pulse Spitter also demonstrated that some native requests are legitimately deferred: the requested mode could appear in `+0xF6C` before `+0xF74` committed.

That is why the mod does **not** manually write `F74` or `F6C`.

---

# Primary mode mapping

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

`21` is not a selectable weapon. It is the pending-idle sentinel.

---

# Installed-mode detection

Hard-coding every possible weapon would be wrong because different multitools have different technologies installed.

Static analysis of an availability helper exposed a compact per-mode table:

```text
global_state + 0x2352D + (mode * 0x10)
```

Configuration:

```text
MODE_TABLE_OFFSET = 0x2352D
MODE_TABLE_STRIDE = 0x10
```

A read-only scanner checked modes `0` through `20`.

## Install/remove validation

The table was validated by physically removing technologies and rescanning.

Examples:

- Removing Scatter Blaster removed mode `1`.
- Removing Boltcaster removed mode `0`.
- Reinstalling Boltcaster restored mode `0`.
- Removing Pulse Spitter removed mode `2`.
- Removing Blaze Javelin removed mode `3`.
- Removing Geology Cannon removed mode `7`.

This showed that the table was useful for dynamically deciding which entries should appear in the wheel.

---

# Modes 9 and 10

A nearly stripped multitool was tested with almost every removable technology taken off.

The remaining nonzero table entries were:

```text
5, 9, 10
```

`5` is the permanent Mining Beam.

Vanilla `G` had nothing useful to cycle to in this state.

Therefore:

```text
9
10
```

are treated as internal/baseline entries rather than normal player-facing weapon choices.

Mode `10` was also special-cased by the availability helper itself.

The wheel filters both.

Mode `8` was observed in some broader configurations but was never isolated confidently enough to expose as a wheel entry.

---

# Primary vs secondary weapons

The first radial implementation initially treated ID `6` like a normal primary mode.

That caused the entry labeled "Paralysis Mortar" to bring out the Plasma Launcher.

This revealed that NMS has separate state for primary weapon mode and secondary/alt-weapon selection.

---

# Finding the secondary selector state

A dedicated read-only **A → B → A** memory probe was written.

Test sequence:

```text
A1 = Plasma Launcher
B  = Paralysis Mortar
A2 = Plasma Launcher
```

The probe sampled the weapon object multiple times at each stage, discarded unstable bytes, and searched for values matching:

```text
A1 == A2
A1 != B
```

This reduced the search to a tiny set of candidates.

The meaningful result was:

```text
weapon_object + 0xF78
```

with:

```text
Plasma Launcher   = 6
Paralysis Mortar = 17
```

The important weapon-object fields were now:

```text
+0xF6C = pending primary
+0xF74 = current primary
+0xF78 = selected secondary
```

---

# Finding the secondary setter

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

Confirmed:

| ID | Secondary weapon |
|---:|---|
| `6` | Plasma Launcher |
| `7` | Geology Cannon |
| `17` | Paralysis Mortar |

Plasma Launcher and Paralysis Mortar were confirmed from the field and native setter trace. Geology Cannon was then validated in-game by installing it, refreshing the wheel state, and selecting it successfully from the radial menu.

---

# Final selection architecture

The wheel has **two native backends**.

## Primary

```text
NMS.exe + 0x13FFB80
```

Arguments:

```text
RCX = weapon_object
EDX = primary mode ID
```

Before calling it, the mod respects `+0xF6C` and refuses to start another primary transition while one is pending.

## Secondary

```text
NMS.exe + 0x1404CE0
```

Arguments:

```text
RCX = weapon_object
EDX = secondary weapon ID
```

Selected secondary state:

```text
weapon_object + 0xF78
```

This split fixed independent selection of Plasma Launcher, Geology Cannon, and Paralysis Mortar.

---

# Radial wheel development

The first real wheel used:

```text
Hold F8
    ↓
Read installed-mode table
    ↓
Build mapped live entries
    ↓
Move mouse away from center
    ↓
Highlight wedge by cursor angle
    ↓
Release F8
    ↓
Queue exactly one native selection
```

## Black-screen rendering failure

The first Tkinter overlay tried to use a fullscreen transparent/color-keyed window.

Over NMS/DirectX it rendered as a black screen.

However, moving the mouse around the black screen and releasing F8 still selected different weapons correctly.

That proved all of these were already working:

- radial angle math;
- mouse tracking;
- press/release lifecycle;
- wedge selection;
- dynamic installed-mode list;
- native weapon dispatch.

Only the rendering method was wrong.

## Known-good overlay

The fullscreen overlay was replaced with a centered:

```text
620 × 620
```

semi-transparent Tkinter window.

This intentionally left a visible square behind the wheel, but it fixed the black-screen problem.

The wheel, highlighting, release-to-select behavior, primary selection, and secondary selection were all confirmed working with this version.

---

# Removing the square

The next UI revision avoids fullscreen color-key transparency.

Instead, it shapes the native Win32 overlay window to the actual wheel geometry using:

```text
CreatePolygonRgn
CombineRgn
SetWindowRgn
```

The idea is that there is physically no window outside the wedges and center circle, so there is no rectangular background to render.

That revision was written but had not yet been user-confirmed when this history was prepared.

---

# Taking over G

F8 was intentionally used during development so the wheel could be tested without competing with vanilla weapon cycling.

The final target is:

```text
Hold G    -> open wheel
Release G -> select highlighted entry
```

Earlier tracing established that NMS receives G through the input path described above.

The Python keyboard-hook implementation has now been **confirmed working in-game** for the radial wheel. Holding `G` opens the wheel and releasing it performs the selected weapon change, while `F8` remains as a fallback/test path.

The already-known native cycle wrapper/routine remains useful as a lower-level fallback if future game or input changes make the higher-level suppression unreliable:

```text
wrapper: 0x1404E40
cycle:   0x1404E80
```

At the time of this write-up, the **G takeover had not yet been user-confirmed in-game**.

---

# Confirmed address summary

> These RVAs/offsets are for the tested NMS build and may change after updates.

## Global and object state

```text
GLOBAL_STATE_PTR_RVA = 0x6E7AAE8
WEAPON_OBJECT_OFFSET = 0x71CA70
```

## Weapon object fields

```text
+0xF6C = pending/requested primary
+0xF74 = current primary
+0xF78 = selected secondary
```

Idle sentinel:

```text
21 / 0x15
```

## Native functions

```text
Primary setter RVA    = 0x13FFB80
Secondary setter RVA  = 0x1404CE0

Cycle wrapper RVA     = 0x1404E40
Cycle routine RVA     = 0x1404E80

SetButton RVA         = 0x2C23BE0
Generic GetButton RVA = 0x2C1DDE0
```

## Installed-mode table

```text
global_state + 0x2352D + (mode * 0x10)
```

---

# Safety rules adopted during development

The current design follows several rules learned from the tracing work:

### Never manually force current/pending fields

Do not directly write `+0xF74`, `+0xF6C`, or `+0xF78` merely to fake a state change.

Use the game's native setters.

### One request per selection

The wheel release creates one request, and that request is consumed before execution so it cannot become a per-frame setter call.

### Respect pending primary transitions

If:

```text
F6C != 21
```

the mod does not start another primary transition.

### Validate native code

The primary setter is guarded by an expected-byte check before invocation.

### Prefer read-only discovery probes

The installed-mode scanner and secondary A/B/A scanner were intentionally read-only.

---

# What did not work

Several failed approaches still helped narrow the problem.

- Early memory candidates were false positives.
- Searching obvious weapon names did not reveal a convenient exported selector.
- The generic GetButton candidate did not expose G in the useful way expected.
- Intrusive setter instrumentation changed normal G behavior and contaminated that capture.
- Fullscreen Tk transparent/color-key rendering blacked out the game.
- Treating secondary weapons as ordinary primary modes produced wrong selections.

---

# Current flow

```text
                ┌─────────────────────┐
                │ Wheel key held      │
                └─────────┬───────────┘
                          │
                          v
                ┌─────────────────────┐
                │ Read mode table     │
                │ IDs 0 .. 20         │
                └─────────┬───────────┘
                          │
                          v
                ┌─────────────────────┐
                │ Filter internal and │
                │ unmapped entries    │
                └─────────┬───────────┘
                          │
                          v
                ┌─────────────────────┐
                │ Draw radial wheel   │
                └─────────┬───────────┘
                          │
                          v
                ┌─────────────────────┐
                │ Mouse selects wedge │
                └─────────┬───────────┘
                          │
                     key released
                          │
              ┌───────────┴───────────┐
              │                       │
              v                       v
     ┌──────────────────┐   ┌──────────────────┐
     │ Primary entry    │   │ Secondary entry  │
     │                  │   │                  │
     │ setter 13FFB80   │   │ setter 1404CE0   │
     └──────────────────┘   └──────────────────┘
```

---

# Why direct selection is better than faking repeated G presses

Simulating repeated G presses would still:

- depend on the current weapon;
- overshoot easily;
- take longer as more technologies are installed;
- make primary/secondary handling awkward;
- depend heavily on timing.

The native approach lets the wheel represent actual targets.

The game can go directly from Mining Beam to Scatter Blaster, or directly change the selected alt weapon from Plasma Launcher to Paralysis Mortar, without cycling through every intermediate technology.

---

# Build/version warning

This was reverse engineered against a live NMS build in late September 2026.

One test launch reported the executable hash:

```text
f22d4dde3eafddfd567915657aa7491eebee2012
```

A game update may invalidate any of the RVAs or layouts above.

Future maintenance should revalidate:

- global-state RVA;
- weapon-object offset;
- current/pending/secondary field offsets;
- primary setter;
- secondary setter;
- cycle routine;
- installed-mode table.

The byte-prefix guard is intended to make the mod fail safely rather than blindly calling an address that no longer contains the expected function.

---

# Next steps

1. Validate/refine the shaped, background-free radial overlay.
2. Confirm G still types normally outside NMS and that foreground-only suppression behaves as intended.
3. Keep native cycle interception as a fallback if Python-level suppression ever becomes unreliable.
4. Improve wheel styling and readability.
5. Add optional icons and clearer primary/secondary visual distinction.
6. Rescan cleanly when the active multitool changes.
7. Add configuration and packaging.
8. Add stronger update/version validation.
9. Map remaining useful unknown IDs such as `8` if needed.

---

# Development takeaway

The biggest lesson was that NMS multitool selection is not one simple weapon-number variable.

There are at least three important pieces of state:

```text
current primary
pending primary transition
selected secondary
```

and two separate native setters are needed for correct direct selection.

The working solution came from combining:

- input tracing;
- static disassembly;
- live native-call observation;
- read-only memory probes;
- install/uninstall experiments;
- A/B/A state comparison;
- hardware write breakpoints;
- and repeated in-game validation.

The result is a radial selector that no longer needs to fake repeated weapon-cycle presses. It can address the game's actual weapon-selection machinery directly.
