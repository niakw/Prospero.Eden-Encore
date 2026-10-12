# R390 — Virtual Switch system buttons on DualSense, without Nintendo system UI

Request: make virtual Switch Capture and HOME available through a DualSense on native PS5, but do NOT invoke Switch system menus, Nintendo screenshots or home-applet behavior. Preserve the actual Sony PS/Home system button. Prepared on development branch, without native PS5 compilation.

## Input routing

| DualSense input | Switch virtual input | Behavior |
|---|---|---|
| Options | ButtonPlus (+) | Existing mapped guest pause/start |
| Touchpad alone | ButtonMinus (-) | Existing 100ms tap pulse / held click |
| Create | ButtonCapture | NEW; only if Create is not assigned to another custom game action |
| Touchpad + Options | ButtonHome | NEW fallback; suppress guest + and - for the full chord |
| PS central button | Sony-only system button | Not exposed by libScePad to the native game, cannot be remapped or suppressed |

Touchpad+L1 (return launcher) and Touchpad+R1 (HUD toggle) take priority and still work. Once the HOME chord activates, suppress both guest Plus/Minus until BOTH buttons are released, preventing a phantom guest pause or Minus action on partial release. Long/short normal touchpad keeps its original Minus behavior. The physical PS button continues to operate the real Sony PS5 UI.

Important: HOME/Capture are system-class controls in a genuine Switch, not ordinary in-game pause inputs. Providing virtual states is different from proving FC27 reacts to these as gameplay controls.

## Disable Switch-side system effects on PS5 only

EmulatedController already binds virtual buttons 18 and 19 to HOME and Screenshot/Capture. Its system_buttons_enabled state defaults true. The upstream AM ButtonPoller would forward their states to WindowSystem::OnSystemButtonPress, causing Nintendo applet/capture activity. Native PS5 source now ignores that AM dispatch but still allows HID system-button states. Non-PS5 builds retain upstream behavior.

Critical CMake detail: PS5_NATIVE compile definition of eden-headless does not propagate to the upstream core static library. Set the compile definition for the exact src/core/hle/service/am/button_poller.cpp TU, without enabling PS5_NATIVE on the rest of core.

## Diagnostics and tests

- Pure GuestSystemButtonRoute finite-state helper prevents HOME chord leakage until both physical buttons release.
- Host C++ AddressSanitizer/UBSan test checks HOME, normal Plus/Minus, button release order, and competing launcher shortcut.
- Existing headless/devices_check.cpp updated to assert new Create->Capture and Touchpad+Options->HOME semantics.
- Source integration check verifies virtual HOME/Capture IDs, protected Nintendo AM dispatcher, scoped CMake macro and controller routing.
- Detailed Logging EDEN_PAD_INPUT_CHAIN is emitted every ~5 seconds, including raw Options, Create, virtual Plus, HOME, Capture edges and Sony-intercepted samples.
- Regression checks wired to future CI; branch uses skip-ci and no native build. No physical PS5 input behavior is claimed validated.

Remaining: validate future native compile and Nintendo guest HID publication in the combined build. No evidence that this particular mapping fixes FC27 freeze.
