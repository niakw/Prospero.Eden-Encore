# Eden Encore — catalogue des fichiers C/C++ hors encore-active : headless

**Branche :** `dev/ps5-sparse-jit`. **Date du relevé :** 17 octobre 2026.

Ce registre complémentaire couvre les **178 chemins** de code, en-têtes et
fragments `.c/.cc/.cpp/.h/.hpp/.inc/.cl` du dossier `headless/`.
Il ne remplace pas `EDEN_ACTIVE_SOURCE_CATALOG.md` : les 222 fichiers
de `vendor/encore-active` sont déjà inventoriés séparément.

**Attention :** une entrée ici ne prouve pas que le fichier est compilé ni
qu'une fonction s'exécute sur console. `launcher/UI` est simplement identifié
pour suivi séparé et n'autorise aucune modification du launcher depuis
l'audit moteur. Un chemin noté « À qualifier » peut avoir été audité sous
une autre forme : il manque seulement la référence de chemin exacte.

- **178** chemins sous `headless/`, dont **59** sources C/C++ et **119** en-têtes/fragments.
- **27** chemins déjà présents dans le graphe moteur.
- **151** chemins sans propriétaire exact dans ce graphe, à trier selon leur rôle réel et leur sélection.
- Les deux générateurs de profils `headless/encore_overrides_generated.h`,
  `headless/glyph_overrides_generated.h` et les autres ressources générées
  sont des entrées de l'inventaire, **pas** de nouveaux patchs CMake.

Le contrôle `tools/check-active-source-inventory.py` confronte les chemins
physiques, la table ci-dessous et les propriétaires du graphe ; il interdit
que des fichiers C/C++ apparaissent dans `headless/` sans être ajoutés
à cette table.

<!-- HEADLESS_SOURCE_CATALOG_START -->
| Chemin | Domaine indicatif | IDs du graphe (chemin exact) | Statut documentaire |
| --- | --- | --- | --- |
| `headless/assets_dir.h` | en-tête/fragment | — | À qualifier |
| `headless/audio.cpp` | runtime/bridge | U04 | Chemin indexé, preuve dépend du graphe |
| `headless/audio_out_init.h` | en-tête/fragment | — | À qualifier |
| `headless/boot_trace.h` | en-tête/fragment | — | À qualifier |
| `headless/buffer_pages.h` | en-tête/fragment | R05 | Chemin indexé, preuve dépend du graphe |
| `headless/buffer_write_ahead.h` | en-tête/fragment | R06 | Chemin indexé, preuve dépend du graphe |
| `headless/button_mapping.h` | en-tête/fragment | — | À qualifier |
| `headless/cache_budget.h` | en-tête/fragment | — | À qualifier |
| `headless/controller_applet.h` | en-tête/fragment | — | À qualifier |
| `headless/crash_report.cpp` | runtime/bridge | U11 | Chemin indexé, preuve dépend du graphe |
| `headless/crash_report.h` | en-tête/fragment | — | À qualifier |
| `headless/crash_site.h` | en-tête/fragment | — | À qualifier |
| `headless/crash_trigger.h` | en-tête/fragment | — | À qualifier |
| `headless/dev_launch_policy.h` | en-tête/fragment | — | À qualifier |
| `headless/dev_render_passes.inc` | en-tête/fragment | — | À qualifier |
| `headless/dev_replay_policy.h` | en-tête/fragment | — | À qualifier |
| `headless/dev_vulkan.h` | en-tête/fragment | — | À qualifier |
| `headless/development_input.h` | en-tête/fragment | — | À qualifier |
| `headless/devices.h` | en-tête/fragment | — | À qualifier |
| `headless/devices_check.cpp` | harness/test | — | À qualifier |
| `headless/diagnostics.h` | en-tête/fragment | — | À qualifier |
| `headless/direct_pool_accounting.h` | en-tête/fragment | — | À qualifier |
| `headless/direct_pool_probe_policy.h` | en-tête/fragment | — | À qualifier |
| `headless/direct_pool_region_scan.h` | en-tête/fragment | — | À qualifier |
| `headless/display_refresh.h` | en-tête/fragment | — | À qualifier |
| `headless/dynarmic/block_range_information.cpp` | JIT/expérimental | U12 | Chemin indexé, preuve dépend du graphe |
| `headless/dynarmic/block_range_information.h` | JIT/expérimental | — | À qualifier |
| `headless/elevation/elevation.cpp` | outil auxiliaire | — | À qualifier |
| `headless/elevation/elevation.hpp` | outil auxiliaire | — | À qualifier |
| `headless/elevation/helper/main.cpp` | outil auxiliaire | — | À qualifier |
| `headless/elevation/protocol.hpp` | outil auxiliaire | — | À qualifier |
| `headless/encore_overrides_generated.h` | données générées | — | À qualifier |
| `headless/encore_overrides_runtime.h` | en-tête/fragment | — | À qualifier |
| `headless/encore_performance_policy.h` | en-tête/fragment | — | À qualifier |
| `headless/error_applet.h` | en-tête/fragment | — | À qualifier |
| `headless/experimental_performance.h` | en-tête/fragment | — | À qualifier |
| `headless/fastmem_handler.cpp` | runtime/bridge | J07 | Chemin indexé, preuve dépend du graphe |
| `headless/filesystem_probe.h` | en-tête/fragment | — | À qualifier |
| `headless/game_liveness.h` | en-tête/fragment | — | À qualifier |
| `headless/glyph_overrides_generated.h` | données générées | — | À qualifier |
| `headless/glyph_overrides_runtime.h` | en-tête/fragment | — | À qualifier |
| `headless/glyph_sha256.h` | en-tête/fragment | — | À qualifier |
| `headless/glyph_version.h` | en-tête/fragment | — | À qualifier |
| `headless/gpu_deferred_replay.h` | en-tête/fragment | M02 | Chemin indexé, preuve dépend du graphe |
| `headless/gpu_deferred_store_publication.h` | en-tête/fragment | M05 | Chemin indexé, preuve dépend du graphe |
| `headless/gpu_deferred_write_queue.h` | en-tête/fragment | — | À qualifier |
| `headless/gpu_dirty_region_split.h` | en-tête/fragment | R04 | Chemin indexé, preuve dépend du graphe |
| `headless/gpu_failure.h` | en-tête/fragment | — | À qualifier |
| `headless/gpu_fault_rate_limit.h` | en-tête/fragment | — | À qualifier |
| `headless/gpu_native_probe.inc` | en-tête/fragment | — | À qualifier |
| `headless/gpu_probe.inc` | en-tête/fragment | — | À qualifier |
| `headless/graphics.cpp` | runtime/bridge | V11 | Chemin indexé, preuve dépend du graphe |
| `headless/graphics.h` | en-tête/fragment | — | À qualifier |
| `headless/guest_fault.h` | en-tête/fragment | — | À qualifier |
| `headless/heap_arenas.inc` | en-tête/fragment | — | À qualifier |
| `headless/heap_guard.h` | en-tête/fragment | — | À qualifier |
| `headless/heap_pages.cpp` | runtime/bridge | U02 | Chemin indexé, preuve dépend du graphe |
| `headless/hle_counters.h` | en-tête/fragment | — | À qualifier |
| `headless/hud.h` | en-tête/fragment | — | À qualifier |
| `headless/image_pages.h` | en-tête/fragment | — | À qualifier |
| `headless/jit-allocator.h` | en-tête/fragment | J06 | Chemin indexé, preuve dépend du graphe |
| `headless/jit-compile-batch.inc` | en-tête/fragment | J10 | Chemin indexé, preuve dépend du graphe |
| `headless/jit-permissions.inc` | en-tête/fragment | J09 | Chemin indexé, preuve dépend du graphe |
| `headless/jit-sparse-commit.h` | en-tête/fragment | J05 | Chemin indexé, preuve dépend du graphe |
| `headless/jit-startup-retry.h` | en-tête/fragment | — | À qualifier |
| `headless/jit_assert.inc` | en-tête/fragment | — | À qualifier |
| `headless/jit_list.h` | en-tête/fragment | J11 | Chemin indexé, preuve dépend du graphe |
| `headless/log_pipe.h` | en-tête/fragment | — | À qualifier |
| `headless/main.cpp` | runtime/bridge | U01 | Chemin indexé, preuve dépend du graphe |
| `headless/memory_check.cpp` | harness/test | J08 | Chemin indexé, preuve dépend du graphe |
| `headless/metadata_bridge.cpp` | runtime/bridge | — | À qualifier |
| `headless/metadata_bridge.h` | en-tête/fragment | — | À qualifier |
| `headless/mock_devices.cpp` | harness/test | — | À qualifier |
| `headless/mock_devices.h` | harness/test | — | À qualifier |
| `headless/mods.h` | en-tête/fragment | — | À qualifier |
| `headless/mods_check.cpp` | harness/test | — | À qualifier |
| `headless/native_directory.h` | en-tête/fragment | — | À qualifier |
| `headless/native_gpu_thread.inc` | en-tête/fragment | — | À qualifier |
| `headless/network_audit.c` | runtime/bridge | U05 | Chemin indexé, preuve dépend du graphe |
| `headless/network_audit.h` | en-tête/fragment | — | À qualifier |
| `headless/network_audit_sockets.c` | runtime/bridge | U06 | Chemin indexé, preuve dépend du graphe |
| `headless/network_domain_rules.c` | runtime/bridge | U07 | Chemin indexé, preuve dépend du graphe |
| `headless/network_domain_rules.h` | en-tête/fragment | — | À qualifier |
| `headless/pad.cpp` | runtime/bridge | U03 | Chemin indexé, preuve dépend du graphe |
| `headless/pad_diagnostics.h` | en-tête/fragment | — | À qualifier |
| `headless/performance.cpp` | runtime/bridge | J01 | Chemin indexé, preuve dépend du graphe |
| `headless/performance.h` | en-tête/fragment | — | À qualifier |
| `headless/pipeline_trace_registry.h` | en-tête/fragment | — | À qualifier |
| `headless/preferences.h` | en-tête/fragment | — | À qualifier |
| `headless/preferences_check.cpp` | harness/test | — | À qualifier |
| `headless/present_interval_witness.h` | en-tête/fragment | — | À qualifier |
| `headless/prosperoeden/eden_services.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/eden_services.h` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/fr_fr_embedded.h` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/frontend.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/frontend.h` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/frontend_stub.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/host/fake_services.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/host/fake_services.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/host/preview_main.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/audio/mixer.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/audio/mixer.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/audio/sounds.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/audio/sounds.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/audio/stream_ring.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/audio/wav.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/audio/wav.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/core/file.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/core/log.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/core/strings.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/core/strings.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/core/tween.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/bidi.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/bidi.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/draw_list.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/draw_list.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/font.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/font.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/font_format.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/gl_batch.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/gl_batch.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/gl_program.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/gl_program.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/harfbuzz.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/image.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/image.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/stream_ring_policy.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/system_fonts.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/gfx/system_fonts.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/platform/audio_out.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/platform/audio_out.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/platform/display_egl.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/platform/display_egl.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/browse.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/dualsense_mask_asset.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/hero_text_layout.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/home.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/launcher.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/launcher.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/library.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/mapping.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/services.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/settings.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/switch_theme.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/textures.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/textures.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/theme.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/video_presets.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/widgets.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/pe/ui/widgets.hpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/radio_input.c` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/radio_input.h` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/runtime_shims.cpp` | launcher/UI | — | À qualifier |
| `headless/prosperoeden/version.h` | launcher/UI | — | À qualifier |
| `headless/ps5_amd_topology_evidence.h` | en-tête/fragment | — | À qualifier |
| `headless/ps5_cpu_topology.h` | en-tête/fragment | — | À qualifier |
| `headless/ps5_guest_system_button_route.h` | en-tête/fragment | — | À qualifier |
| `headless/ps5_net_compat.c` | runtime/bridge | U08 | Chemin indexé, preuve dépend du graphe |
| `headless/romfs_check.cpp` | harness/test | — | À qualifier |
| `headless/ryujinx_check.cpp` | harness/test | — | À qualifier |
| `headless/ryujinx_saves.h` | en-tête/fragment | — | À qualifier |
| `headless/scalar_check.cpp` | harness/test | — | À qualifier |
| `headless/sdk_audit.h` | en-tête/fragment | — | À qualifier |
| `headless/settings_store.h` | en-tête/fragment | — | À qualifier |
| `headless/shader_cache_check.cpp` | harness/test | — | À qualifier |
| `headless/shader_cache_reader.inc` | en-tête/fragment | — | À qualifier |
| `headless/stall_watchdog.h` | en-tête/fragment | — | À qualifier |
| `headless/stop_limit.cpp` | runtime/bridge | — | À qualifier |
| `headless/stop_limit.h` | en-tête/fragment | — | À qualifier |
| `headless/storage_paths.h` | en-tête/fragment | — | À qualifier |
| `headless/title_id_fallback.h` | en-tête/fragment | — | À qualifier |
| `headless/vulkan_allocator.cpp` | runtime/bridge | U10 | Chemin indexé, preuve dépend du graphe |
| `headless/vulkan_gc_budget.h` | en-tête/fragment | — | À qualifier |
| `headless/vulkan_pool_capacity.h` | en-tête/fragment | — | À qualifier |
| `headless/vulkan_surface.cpp` | runtime/bridge | U09 | Chemin indexé, preuve dépend du graphe |
| `headless/watch.h` | en-tête/fragment | — | À qualifier |
| `headless/zbic_compression.cpp` | runtime/bridge | — | À qualifier |
| `headless/zbic_compression.h` | en-tête/fragment | — | À qualifier |
<!-- HEADLESS_SOURCE_CATALOG_END -->

## Priorités de qualification

La priorité technique se porte sur les unités `runtime/bridge`,
`JIT/expérimental`, les en-têtes réellement sélectionnés et les
fonctions CPU/GPU/mémoire ; les fichiers du launcher restent dans
le chantier UI indépendant. Les programmes de test ne doivent pas être
confondus avec des overrides de production. Une source réellement sélectionnée
avec un comportement corrigé doit acquérir une entrée fonctionnelle
dans `EDEN_CORE_AUDIT_DEPENDENCIES.md`, puis une preuve indépendante.
