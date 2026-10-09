# Whole-Switch-1 PlayStation UI glyph discovery & multiplatform adaptation

Updated 2026-10-10 — `dev/ps5-sparse-jit`

## Purpose

Discover controller button/prompt mods across **all** Switch 1 games,
including same-game mods initially published on **PC, Wii U, Xbox, PlayStation
and PSP**, instead of maintaining a short BOTW-only set. Generate
texture-adaptation candidates without copying existing mods' artwork or
overwriting game-owned graphics.

**Real first corpus run:** 24,205 distinct Switch 1 base title IDs
from public four-region TitleDB metadata (US, GB, JP, FR) on
[GitHub Actions #38004965979](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38004965979).
This number is a community catalog snapshot, **not** a complete official
Nintendo inventory, 24k supported games, or 24k discovered mods.

## Automation components

| Tool | Function | Automatically alters runtime? |
| --- | --- | --- |
| `ps-glyph-switch1-corpus.py` | Deduplicate game names / regional Title IDs, retain aliases and existing research priority | No |
| `ps-glyph-mod-discovery.py` | Incremental DuckDuckGo, GitHub search, official credentialed Yandex search; PC/Switch/multilingual query variants and state by Title ID **and** console query | No |
| `ps-glyph-mod-results-merge.py` | Merge batches, collapse duplicate links and preserve providers / query provenance | No |
| `ps-glyph-multiplatform-adapt.py` | Match PC/Wii U/PSP/PS4 titles to Switch IDs and choose per-engine extraction/adaptation tools | No |
| `ps-glyph-multiplatform-image-port.py` | Reuse same-game source-mod UI positions in an independently decoded original Switch texture, **even if graphic art or pixel size differs** | No, candidate only |
| `ps-glyph-mod-zip-positions.py` | Decode direct Switch ROMFS mod original-versus-patched ASTC/BNTX/Yaz0/SARC and derive actual altered pixels | No |
| `ps-glyph-mod-auto-plan.py` | Match isolated Switch sprites and scene/guest input meanings; export reviewed per-resource manifest | No |
| `ps-glyph-botw-auto-pack.py` + `ps-glyph-botw-stage-pack.py` | Regenerate independently authored PS icons into checked ASTC blocks and stage a local-only LayeredFS replacement | No automatic activation |

Engine format routes are **not all implemented**. The current precise
BNTX ASTC host codec path supports a subset of Switch Nintendo native UI
resources; Unity, Unreal, Persona CPK/SPR, Klei TEX/Lua and BFRES layouts
need their original-game container exporters/repackers. The adapter reports
that missing prerequisite instead of misclassifying a PC asset as a
Switch-ready pack. Different versions of a game may use different materials
and scenes.

## Search engines and source websites

Search links are generated for each title and optional online queries
inspect **metadata / search result links only**, with allowlisted sources
including GameBanana, Nexus Mods, ModDB, GitHub, GBAtemp, ModWorkshop,
Thunderstore and CurseForge. Search wording cycles through Nintendo
Switch, PlayStation / DualSense, multiplatform PC/Wii U/Xbox, and
Russian `кнопки/иконки` variants. DuckDuckGo is treated as a public
rate-limited provider, stopping on bot challenges/403/429. Yandex Search
API is metered and needs explicit
`YANDEX_SEARCH_API_KEY` and `YANDEX_SEARCH_FOLDER_ID` in GitHub Secrets:
**no paid Yandex requests by default**.

Use `tools/ps-glyph-mod-discovery.py` to produce text/source lead records,
not ZIP binaries. A title matching a GitHub repo/website remains
**unverified** until source format, version and corresponding Switch title
and original pixels have been checked.

## GitHub source discovery and limits

`.github/workflows/discover-switch1-glyph-mods.yml` runs limited
**free GitHub source searches** on development-branch pushes and checks
one Switch UI and one corresponding PC/multiplatform query variant per
bounded game batch. Incremental source metadata and search progress are
stored under Actions cache, plus downloadable reports in Actions artifacts.
Do not insert a Yandex key unless billing has been approved.

GitHub scheduled `cron` workflows only run on the repository's
**default branch**; the protected/default branch is currently different
from `dev/ps5-sparse-jit`. The discovery workflow therefore does not
claim autonomous nightly sweeps while it remains dev-only. Pushing a
source/workflow change triggers the bounded free pass; an eligible
workflow_dispatch run can select the provider and 1–250 title batch,
subject to GitHub workflow default-branch dispatch policy.

## Adapting existing console mods, not redrawing scene coordinates

The same game may keep UI/controller help positions across PS4/Wii U/PC
and Switch even when sprite atlases, source file offsets and compression
differ. We transfer **scene-normalized coordinates** as a prior, then
confirm the actual Switch original sprite on decoded pixels and source
hash. The mod source may provide the original changed XYWH directly.
Our artwork uses the supplied PS5 symbol atlas with proper attribution;
we do not bundle a third-party modified Nintendo texture.

For fixed PS5 input: Nintendo guest action `A` → Cross (bottom),
`B` → Circle (right), `X` → Square (left), `Y` → Triangle (top).
A physical controller silhouette still shows Circle on the right,
Cross at the bottom. A mod screenshot alone does not tell which semantics
the current scene uses.

An experimental candidate is **not** a verified emulation feature:
the per-game version, exact Switch original SHA-256, atlas/scene/symbol
mapping, permitted artwork and real PS5 rendering are separately tracked.
The native glyph catalogue still reports zero publicly qualified built-in
packs. This work never validates FC27 frame times/VRAM/JIT.
