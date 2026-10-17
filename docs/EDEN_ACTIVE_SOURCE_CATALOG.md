# Eden Encore — inventaire exhaustif des sources actives

**Branche :** `dev/ps5-sparse-jit`. **Relevé :** 17 octobre 2026.

Cet inventaire recense chaque fichier C/C++, en-tête et fragment source
(`.c`, `.cpp`, `.h`, `.hpp`, `.inc`, ainsi que les variantes voisines)
présent sous `vendor/encore-active`. Il est généré depuis l'arbre réel
et contrôlé par `tools/check-active-source-inventory.py`.

- **183 fichiers** de code et d'en-têtes enregistrés.
- **43 fichiers** possèdent une correspondance de chemin *exacte*
  avec une ou plusieurs lignes du registre de fonctions.
- **140 fichiers** n'ont pas encore de ligne de graphe correspondant
  exactement à leur chemin. Cela **ne prouve pas** qu'ils n'ont jamais été
  examinés, ni qu'ils sont effectivement compilés.
- Les `backport-staging` sont des sources de snapshot préparées ;
  `driver-fork` représente la dépendance graphique modifiée ;
  `maintained-override` les unités et en-têtes Encore.

**Important :** une correspondance de chemin n'est ni un test hôte,
ni une certification console. Le graphe
`docs/EDEN_CORE_AUDIT_DEPENDENCIES.md` porte les contrats fonctionnels,
leurs états et les preuves. L'inventaire des 57 générateurs CMake
principaux, 21 générateurs de modules, sept modules indirects et 46 patches
reste dans `docs/EDEN_OVERRIDE_MIGRATION_INVENTORY.md`.

<!-- ACTIVE_SOURCE_CATALOG_START -->
| Chemin relatif à `vendor/encore-active/` | Famille | IDs du graphe (chemin exact) |
| --- | --- | --- |
| `eden-backports/src/audio_core/audio_render_manager.cpp` | `backport-staging` | — |
| `eden-backports/src/common/logging.cpp` | `backport-staging` | — |
| `eden-backports/src/common/net/net.cpp` | `backport-staging` | — |
| `eden-backports/src/common/settings.cpp` | `backport-staging` | — |
| `eden-backports/src/common/settings.h` | `backport-staging` | — |
| `eden-backports/src/common/settings_enums.h` | `backport-staging` | — |
| `eden-backports/src/core/device_memory_manager.h` | `backport-staging` | — |
| `eden-backports/src/core/device_memory_manager.inc` | `backport-staging` | — |
| `eden-backports/src/core/file_sys/system_archive/system_version.cpp` | `backport-staging` | — |
| `eden-backports/src/core/frontend/applets/controller.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/api_version.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/kernel/k_scheduler.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/kernel/k_slab_heap.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/kernel/k_thread.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/kernel/svc/svc_info.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/kernel/svc_types.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/acc/acc.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/acc/acc.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/am/display_layer_manager.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/am/frontend/applets.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/am/lifecycle_manager.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/am/service/application_creator.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/am/service/library_applet_accessor.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/am/service/library_applet_creator.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/am/service/self_controller.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/am/service/self_controller.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/audio/audio.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/bcat/bcat.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/bpc/bpc.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/filesystem/filesystem.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/filesystem/fsp/fsp_srv.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/filesystem/fsp/fsp_srv.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/glue/arp.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/glue/glue.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/grc/grc.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/hid/hid_system_server.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ldr/ldr.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/nfp/nfp.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ngc/ngc.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/nifm/nifm.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ns/application_manager_interface.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ns/application_manager_interface.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ns/i_async_result.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ns/i_async_result.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ns/ns.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ns/read_only_application_control_data_interface.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/nvdrv/devices/nvmap.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/nvnflinger/buffer_queue_core.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/nvnflinger/buffer_queue_core.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/olsc/transfer_task_list_controller.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/olsc/transfer_task_list_controller.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/pctl/parental_control_service.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/pctl/parental_control_service.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/pctl/pctl_types.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/pm/pm.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/ro/ro.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/set/settings.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/sm/sm.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/sockets/bsd.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/sockets/bsd.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/sockets/encore_guest_network_policy.h` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/sockets/sfdnsres.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/sockets/sockets.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/usb/usb.cpp` | `backport-staging` | — |
| `eden-backports/src/core/hle/service/wlan/wlan.cpp` | `backport-staging` | — |
| `eden-backports/src/core/memory.cpp` | `backport-staging` | — |
| `eden-backports/src/hid_core/resources/npad/npad.cpp` | `backport-staging` | — |
| `eden-backports/src/video_core/buffer_cache/buffer_cache.h` | `backport-staging` | — |
| `eden-backports/src/video_core/buffer_cache/buffer_cache_base.h` | `backport-staging` | — |
| `eden-backports/src/video_core/control/channel_state_cache.h` | `backport-staging` | — |
| `eden-backports/src/video_core/dma_pusher.cpp` | `backport-staging` | — |
| `eden-backports/src/video_core/engines/kepler_compute.cpp` | `backport-staging` | — |
| `eden-backports/src/video_core/engines/kepler_compute.h` | `backport-staging` | — |
| `eden-backports/src/video_core/engines/sw_blitter/blitter.cpp` | `backport-staging` | — |
| `eden-backports/src/video_core/fence_manager.h` | `backport-staging` | — |
| `eden-backports/src/video_core/query_cache/query_cache.h` | `backport-staging` | — |
| `eden-backports/src/video_core/renderer_vulkan/vk_buffer_cache.cpp` | `backport-staging` | — |
| `eden-backports/src/video_core/renderer_vulkan/vk_buffer_cache.h` | `backport-staging` | — |
| `eden-backports/src/video_core/texture_cache/texture_cache.h` | `backport-staging` | — |
| `eden-backports/src/video_core/texture_cache/texture_cache_base.h` | `backport-staging` | — |
| `eden-backports/src/video_core/texture_cache/util.cpp` | `backport-staging` | — |
| `eden-core/include/core/file_sys/bis_factory.h` | `maintained-override` | F13 |
| `eden-core/overrides/core/device_memory_manager.inc` | `maintained-override` | — |
| `eden-core/overrides/core/gpu_dirty_memory_manager.h` | `maintained-override` | — |
| `eden-core/overrides/core/guest_memory.h` | `maintained-override` | — |
| `eden-core/src/audio_core/renderer/voice/voice_info.cpp` | `maintained-override` | — |
| `eden-core/src/audio_core/sink/sink_details.cpp` | `maintained-override` | — |
| `eden-core/src/audio_core/sink/sink_stream.cpp` | `maintained-override` | A03 |
| `eden-core/src/common/assert.h` | `maintained-override` | — |
| `eden-core/src/common/cpu_features.cpp` | `maintained-override` | F07 |
| `eden-core/src/common/fiber.cpp` | `maintained-override` | J18 |
| `eden-core/src/common/fs/fs.cpp` | `maintained-override` | F06 |
| `eden-core/src/common/fs/path_util.cpp` | `maintained-override` | F08 |
| `eden-core/src/common/logging.cpp` | `maintained-override` | — |
| `eden-core/src/common/thread.cpp` | `maintained-override` | F05 |
| `eden-core/src/core/file_sys/bis_factory.cpp` | `maintained-override` | F14 |
| `eden-core/src/core/file_sys/fsmitm_romfsbuild.cpp` | `maintained-override` | F12 |
| `eden-core/src/core/file_sys/savedata_factory.cpp` | `maintained-override` | F15 |
| `eden-core/src/core/hle/kernel/k_spin_lock.cpp` | `maintained-override` | H30 |
| `eden-core/src/core/hle/kernel/svc/svc_ipc.cpp` | `maintained-override` | H21 |
| `eden-core/src/core/hle/service/am/service/application_functions.cpp` | `maintained-override` | H32 |
| `eden-core/src/core/hle/service/filesystem/filesystem.cpp` | `maintained-override` | F11 |
| `eden-core/src/core/hle/service/filesystem/fsp/fs_i_file.cpp` | `maintained-override` | F02 |
| `eden-core/src/core/hle/service/filesystem/fsp/fs_i_filesystem.cpp` | `maintained-override` | F04 |
| `eden-core/src/core/hle/service/filesystem/fsp/fs_i_storage.cpp` | `maintained-override` | F03 |
| `eden-core/src/core/hle/service/nvdrv/devices/nvhost_ctrl.cpp` | `maintained-override` | N02,N05 |
| `eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp` | `maintained-override` | N03 |
| `eden-core/src/core/hle/service/service.cpp` | `maintained-override` | H22,H28 |
| `eden-core/src/core/internal_network/network_interface.cpp` | `maintained-override` | F10 |
| `eden-core/src/core/loader/deconstructed_rom_directory.cpp` | `maintained-override` | F16 |
| `eden-core/src/hid_core/resource_manager.cpp` | `maintained-override` | H31 |
| `eden-core/src/video_core/texture_cache/util.h` | `maintained-override` | — |
| `eden-core/src/video_core/video_core_opengl.cpp` | `maintained-override` | V12 |
| `eden-gpu/gpu_thread_dev.cpp` | `maintained-override` | Q03 |
| `eden-gpu/gpu_thread_quiet.cpp` | `maintained-override` | — |
| `eden-gpu/include/common/bounded_threadsafe_queue.h` | `maintained-override` | — |
| `eden-gpu/include/video_core/gpu_thread.h` | `maintained-override` | — |
| `eden-shader/src/shader_recompiler/frontend/maxwell/translate/impl/load_store_local_shared.cpp` | `maintained-override` | — |
| `eden-surface-lifecycle/src/core/hle/service/nvnflinger/surface_flinger.cpp` | `maintained-override` | — |
| `eden-sync/src/core/hle/kernel/k_synchronization_object.h` | `maintained-override` | H17 |
| `eden-threading/src/core/hle/kernel/k_address_arbiter.cpp` | `maintained-override` | H07,H10,H11 |
| `eden-threading/src/core/hle/kernel/k_condition_variable.cpp` | `maintained-override` | H01,H08,H09 |
| `eden-threading/src/core/hle/kernel/k_scheduler.cpp` | `maintained-override` | H02,H18,H20 |
| `eden-threading/src/core/hle/kernel/k_slab_heap.h` | `maintained-override` | — |
| `eden-threading/src/core/hle/kernel/k_thread.cpp` | `maintained-override` | H03,H19 |
| `eden-threading/src/core/hle/kernel/k_thread.h` | `maintained-override` | — |
| `eden-threading/src/core/hle/kernel/k_worker_task_manager.h` | `maintained-override` | — |
| `eden-threading/src/core/hle/kernel/slab_helpers.h` | `maintained-override` | — |
| `eden-threading/src/core/hle/kernel/svc/svc_address_arbiter.cpp` | `maintained-override` | H13 |
| `eden-threading/src/core/hle/kernel/svc/svc_condition_variable.cpp` | `maintained-override` | H12 |
| `eden-threading/src/core/hle/kernel/svc/svc_synchronization.cpp` | `maintained-override` | H14 |
| `eden-threading/src/core/hle/kernel/svc/svc_thread.cpp` | `maintained-override` | H15 |
| `eden-vulkan/include/core/frontend/emu_window.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/present.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/pipeline_helper.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/present/window_adapt_pass.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/renderer_vulkan.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/striped_wait.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/vk_blit_screen.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/vk_compute_pipeline.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/vk_descriptor_buffer.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h` | `maintained-override` | V10 |
| `eden-vulkan/include/video_core/renderer_vulkan/vk_present_manager.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/vk_scheduler.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/vulkan_common/vulkan.h` | `maintained-override` | — |
| `eden-vulkan/include/video_core/vulkan_common/vulkan_wrapper.h` | `maintained-override` | — |
| `eden-vulkan/vk_buffer_cache_cost.cpp` | `maintained-override` | R03 |
| `eden-vulkan/vk_compute_pass_cost.cpp` | `maintained-override` | — |
| `eden-vulkan/vk_compute_pipeline_cost.cpp` | `maintained-override` | — |
| `eden-vulkan/vk_descriptor_buffer_cost.cpp` | `maintained-override` | — |
| `eden-vulkan/vk_fence_manager_cost.cpp` | `maintained-override` | — |
| `eden-vulkan/vk_graphics_pipeline_cost.cpp` | `maintained-override` | — |
| `eden-vulkan/vk_multi_range_buffer_cost.cpp` | `maintained-override` | — |
| `eden-vulkan/vk_pipeline_cache_cost.cpp` | `maintained-override` | V07 |
| `eden-vulkan/vk_texture_cache_cost.cpp` | `maintained-override` | — |
| `eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h` | `maintained-override` | — |
| `eden-vulkan/vulkan_blit_screen.cpp` | `maintained-override` | — |
| `eden-vulkan/vulkan_descriptor_buffer.cpp` | `maintained-override` | — |
| `eden-vulkan/vulkan_device.cpp` | `maintained-override` | — |
| `eden-vulkan/vulkan_hud_shaders.h` | `maintained-override` | — |
| `eden-vulkan/vulkan_instance.cpp` | `maintained-override` | — |
| `eden-vulkan/vulkan_library.cpp` | `maintained-override` | — |
| `eden-vulkan/vulkan_present_layer.cpp` | `maintained-override` | V09 |
| `eden-vulkan/vulkan_present_manager.cpp` | `maintained-override` | V02 |
| `eden-vulkan/vulkan_query_cache.cpp` | `maintained-override` | — |
| `eden-vulkan/vulkan_rasterizer.cpp` | `maintained-override` | V05,V08 |
| `eden-vulkan/vulkan_renderer.cpp` | `maintained-override` | V04 |
| `eden-vulkan/vulkan_scheduler.cpp` | `maintained-override` | V01 |
| `eden-vulkan/vulkan_swapchain.cpp` | `maintained-override` | V03 |
| `eden-vulkan/vulkan_window_adapt_pass.cpp` | `maintained-override` | — |
| `eden-vulkan/vulkan_wrapper.cpp` | `maintained-override` | — |
| `ps5-mesa/src/amd/vulkan/meta/radv_meta_clear.c` | `driver-fork` | — |
| `ps5-mesa/src/amd/vulkan/meta/radv_meta_resolve.c` | `driver-fork` | — |
| `ps5-mesa/src/amd/vulkan/radv_cmd_buffer.c` | `driver-fork` | — |
| `ps5-mesa/src/amd/vulkan/radv_descriptor_update_template.c` | `driver-fork` | — |
| `ps5-mesa/src/amd/vulkan/radv_descriptor_update_template.h` | `driver-fork` | — |
| `ps5-mesa/src/amd/vulkan/radv_physical_device.c` | `driver-fork` | — |
| `ps5-mesa/src/amd/vulkan/radv_pipeline.c` | `driver-fork` | — |
| `ps5-mesa/src/amd/vulkan/winsys/ps5/radv_ps5_platform.c` | `driver-fork` | — |
| `ps5-mesa/src/amd/vulkan/winsys/ps5/radv_ps5_winsys.c` | `driver-fork` | — |
| `ps5-mesa/src/util/disk_cache_os.c` | `driver-fork` | — |
| `ps5-mesa/src/vulkan/wsi/wsi_common_videoout.c` | `driver-fork` | — |
<!-- ACTIVE_SOURCE_CATALOG_END -->

## Critères de tenue à jour

Chaque nouveau fichier C/C++ ou en-tête introduit dans le fork doit figurer
dans ce tableau, même s'il n'a pas encore été qualifié. Tout déplacement ou
retrait doit mettre à jour la liste et les liens du graphe.

Pour les lignes « — », le prochain travail consiste à déterminer
le **propriétaire de compilation**, le fichier épinglé correspondant, les
fonctions réellement modifiées, les tests et les dépendances, avant de les
marquer comme vérifiées. Ne pas gonfler artificiellement les résultats HOST.
