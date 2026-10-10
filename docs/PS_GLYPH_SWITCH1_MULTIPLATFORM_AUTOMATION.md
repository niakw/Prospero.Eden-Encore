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
This number is a community **unverified base-application-shaped TitleDB
record count**, **not** 24k officially released Switch 1 games. It is an
unqualified historical snapshot: entries may be demos, unreleased releases,
cloud editions or storefront variations. The strict eligibility gate now
screens this source before any NEW full-crawl snapshot is admitted. No
arbitrary 4k-8k limit is imposed, and official platform validation is not
inferred from IDs alone.

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

## 10 October — Stable storage and Firefox-style public search

- **Simple client first:** `tools/ps-glyph-curl-search.py` runs public
  DuckDuckGo/Yandex HTML searches with `curl --user-agent
  "Mozilla/5.0 ... Firefox/140.0"`. This is an HTTP User-Agent, **not
  a full Firefox browser**. If content needs JavaScript, explicitly use
  `tools/ps-glyph-firefox-search.py` (Playwright's actual Firefox), installed
  only for manually selected browser jobs. Neither path solves a CAPTCHA
  or impersonates an authorized logged-in user.
- **No paid Yandex API by default.** `curl_yandex` and
  `firefox_yandex` navigate publicly available Yandex search pages;
  `yandex` remains the separate credentialed, metered official API.
  Public search engines may still refuse requests from GitHub datacenters.
  A 403/429/challenge is a failed/unprocessed query, never a successful scan.
- **Persistent GitHub store:** [`data/glyph-research/README.md`](../data/glyph-research/README.md)
  and [BOTW `01007EF00011E000.json`](../data/glyph-research/games/01007EF00011E000.json).
  `discovery/leads.json` retains checked public source links per game,
  `discovery/progress.json` persists provider/variant Title ID checkpoints,
  `catalog/switch1-titles.json.gz` and `catalog/source-queries.json.gz`
  preserve the entire 24,205-title snapshot and 96,820 prepared searches
  without keeping 100k loose files. **Do not infer 96,820 actual searches.**
- GitHub Actions merges discoveries with existing git data, refetches the
  latest `dev/ps5-sparse-jit` before committing, and retries on concurrent
  source commits; it never force-pushes and never writes the main/release
  branch. A denied push remains a warning and the downloadable workflow
  artifact is only a temporary fallback. No Nintendo game assets, mods,
  cookies or raw search-result HTML belong in the repository.


## Périmètre strict — Switch 1 uniquement (2026-10-10)

- **Inclure** un jeu disposant d'une version native Nintendo Switch 1,
  même s'il est également disponible sur Switch 2, PC, Wii U, PlayStation
  ou Xbox. Seules les données nécessaires à la **version Switch 1** peuvent
  être utilisées pour préparer un patch exécutable.
- **Exclure** les titres **Switch 2 seulement** : leur application native
  utilise généralement la famille de Title ID `0400…`, pas `0100…`.
  Les éditions Switch 2 ne fournissent pas, à elles seules, une preuve de
  compatibilité des textures/ROMFS avec la Switch 1.
- **Exclure ou différer** les démos clairement identifiées, DLC/updates,
  applications non ludiques, versions cloud-only et titres non encore sortis
  dans les métadonnées disponibles. Un identifiant `0100…000` reste un
  **candidat**, pas une preuve de jeu officiellement sorti.
- Ne **pas transformer** la fourchette d'inventaires tiers « 4 000–8 000 »
  en plafond forcé : les méthodes de comptage, régions, jeux numériques
  et dates diffèrent. La source autoritative de plateforme est la fiche
  Switch 1 du jeu ou ses métadonnées d'application d'origine, pas une
  estimation statistique.
- Script de contrôle : `tools/ps-glyph-switch1-eligibility.py`, tests
  `tools/check-ps-glyph-switch1-eligibility.py`, et corpus
  `tools/ps-glyph-switch1-corpus.py`. Ils produisent les compteurs
  `raw_switch1_application_ids`, `switch2_only_id_rows_excluded`,
  `non_game_or_pre_release_title_ids_excluded`,
  `officially_verified_switch1_game_count`. Les sources sans preuve
  officielle restent marquées comme non vérifiées.
- Le crawler long refuse le **vieux catalogue non qualifié** et attend la
  rematérialisation de `catalog/switch1-titles.json.gz` avant de continuer.
  L'historique de recherches déjà effectué n'est pas supprimé.


## Scope matériel corrigé — Switch 1 uniquement (10 octobre 2026)

- **Inclure :** toute version de jeu exécutée sur la **Nintendo Switch 1**
  (y compris les jeux qui ont aussi une version Switch 2, une Switch 2
  Edition ou une mise à niveau sur la nouvelle console).
- **Exclure :** les jeux natifs / exclusifs Nintendo Switch 2 (`0400…`),
  même s'ils sont disponibles dans les mêmes boutiques ou séries.
  BOTW Switch 1 : `01007EF00011E000`, conservé. Mario Kart World :
  `0400C3F00006E000`, exclu.
- **Méthode :** la source `blawar/titledb` sert de métadonnées candidates
  Switch 1, avec validation des IDs d'application `0100…000`.
  Les éditions Switch 2 `0400` ne sont jamais converties arbitrairement
  en faux titres Switch 1.
- **Comptage :** 24 205 correspond au nombre d'**IDs candidats dédupliqués
  par région**, et non à 24 205 sorties commerciales uniques vérifiées.
  Le rapport `data/glyph-research/catalog/scope-audit.json` expose les
  noms d'affichage répétés et les indices de démos/cloud sans supprimer un
  titre sur une simple règle textuelle.
- **Validation :** `tools/check-ps-glyph-switch1-corpus.py` vérifie
  les versions Switch 1 conservées et les exclusivités 2 écartées ;
  `tools/check-ps-glyph-store-research.py` refuse les IDs `0400`
  dans le stockage persistant. Les 96 820 liens de recherche préparés
  ne sont pas 96 820 requêtes réellement exécutées.
