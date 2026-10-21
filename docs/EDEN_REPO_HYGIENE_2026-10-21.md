# Eden Encore — repository hygiene / coherence review (21 October 2026)

Branch: `dev/ps5-sparse-jit`. Review scope: **tracked Git tree**, not local untracked files on a Mac or PS5.

## Removed safely

- `assets/launch-background-source.png` (6,124,440 bytes): its Git blob was byte-identical to `assets/background-source.png`. The canonical editable image remains. Release packaging instead uses `assets/encore-background.jpg` and the baked launcher `backdrop.tga`, so this removal does not change the compiled rendering code or runtime resources. It saves working-tree space; Git already deduplicated the identical blob internally.

## Retained deliberately

- `assets/icon0.png` and `sce_sys/icon0.png`: identical bytes but both paths are referenced by release metadata, checks and package layout. No deletion.
- `vendor/sources/`, `vendor/objects/`, `vendor/encore-active/`: original pinned source closure, verified archive chunks and active maintained source. These are different provenance roles and must not be deduplicated by deleting arbitrary files.
- Historical dated audit reports and source-parity fixtures: evidence and independent regression oracles, not disposable build output.
- Launcher sources and generated UI art: still part of the dedicated launcher review, not included as newly optimized engine files.

## Preventive guard

- `.gitignore` now covers additional native CMake/Ninja intermediates and host coverage/profiling outputs.
- `tools/ci/check-repo-hygiene.py` rejects these if tracked in first-party paths, validates 12 workflow permission declarations and tracked script references, and forbids reintroducing the redundant background alias while retaining its canonical source.

## CI/release boundary

Previous HEAD `c3ac33a` had green source preflight, core fast gate and CodeQL, with the full native package build still underway at audit time. The next build and console game qualification remain separate. No performance, FPS or crash-fix claim follows from repository hygiene.

**Progress counters:** 429/429 engine sources reviewed; 0 engine sources unexamined, 62 launcher/UI sources tracked separately. “Reviewed” does not mean every file was rewritten or accelerated. A historic report's older “files to optimize” counter must not be read as the current number of unexamined engine owners.
