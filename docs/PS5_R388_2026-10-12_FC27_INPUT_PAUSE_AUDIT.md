# R388 — FC27 apparent freeze: can a Switch-only Pause / HOME command be missing?

Source: user-provided R384 `stderr(20261012-174838).log`, `heap(10).log`; reviewed `headless/pad.cpp`, `headless/button_mapping.h`, `third_party/ps5_pad.hpp`, `headless/main.cpp`, `headless/controller_applet.h` (dev/ps5-sparse-jit).

**Static mapping:** FC27 startup `EDEN_PAD_MAPPING_FIXED layout=0 a=0 b=1 x=2 y=3 title_override=1`; user-selected profile is static through menus, cinematics and matches. DualSense **Options maps to Switch Plus** (normal in-game pause), Cross=A, Circle=B, Square=X, Triangle=Y. Touchpad is Minus with a delayed tap; Touchpad+L1 and Touchpad+R1 are reserved shortcuts. HOME/CAPTURE virtual controls exist upstream but no DualSense input maps to them; those are typically system-level Switch inputs, not title pause.

**The actual Sony interception bit:** `intercepted_samples` in Pad::Poll increments on `kButtonIntercepted=0x80000000`; `is_usable` returns false and Pad::Consume neutralizes such samples. It does NOT count launcher shortcut interception. First nonzero is poll=328750 versus approximate repetitive guest-workload onset at poll=272500 (~225s later at 250 polls/s). Therefore late PS5 system interception cannot alone explain the start of the repeated-workload period.

**After plateau start:** physical face-button edge counter increases by 62, including Cross +4, Circle +9, Square +5, Triangle +1. 927566 total controller samples, 926437 usable, 1129 marked intercepted, 0 read errors, connected=1. R384 does NOT record Options rising edges, virtual Switch Plus events published, or emulated guest Npad transitions; delivery or failure of the pause command remains unproven. Workload similarity cannot prove frames are pixel-identical or gameplay is waiting for an input.

**Next combined diagnostic build (not a user test yet):** add one summary every 5s when detailed logs enabled with physical Options rising edges; virtual ButtonPlus/A/B changes actually emitted by PadEngine; emulator HID Npad Plus/A/B shared-memory publication and style, separately; all tagged by source commit. Compare alongside guest PC/IPC/Opus progression and any applet state. Never fabricate a HOME press or auto-resume guest gameplay, and do not flip face-button mapping globally.

Full offline audit and re-usable parser are also available in the conversation files `eden-r388-hypothese-pause-switch.md`, `eden-r388-input-freeze-analysis.json` and `analyze_eden_fc27_input_freeze.py`.

**Status:** forensic diagnosis only; no runtime fix, no native compile and no extra console test requested.

## R389 — diagnostic partiellement implémenté (branch only)

Commits `9e54cd548` et `adc3d3eb8` : `headless/devices.h` / `headless/pad.cpp` comptent les nouveaux fronts physiques `Options` et les fronts montants `ButtonPlus` effectivement publiés par le moteur virtuel. Un unique `EDEN_PAD_INPUT_CHAIN` est émis toutes les 1 250 itérations (~5 secondes) **seulement avec Detailed Logging**, sans modifier le mapping ni injecter de boutons. Test de source `tools/check-ps5-pad-input-chain.py`, commit `00af8967b`.

**Ne pas confondre `published_plus_edges` avec une lecture de la mémoire partagée Npad par le jeu.** Le troisième maillon HID et le diagnostic des applets restent à instrumenter. Aucun build PS5 ni essai console pour ces changements.
