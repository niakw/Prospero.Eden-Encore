#!/usr/bin/env python3
"""Apply the pinned Eden display-lifetime adaptation to the Mesa build export."""
from pathlib import Path
import hashlib
import sys

root = Path(__file__).resolve().parents[1]
# R343: a legacy, reproducible SOURCE EQUIVALENCE ORACLE, not used by build.
# Compare the complete checked-in modified RADV files against this generator.
if sys.argv[1:2] == ['--check']:
    expected = hashlib.sha256((root/'vendor/encore-active/ps5-mesa/src/vulkan/wsi/wsi_common_videoout.c').read_bytes()).hexdigest()
    marker = Path(sys.argv[2]) if len(sys.argv) == 3 else None
    recorded = marker.read_text().split()[0] if marker and marker.is_file() else ''
    sys.exit(0 if expected == recorded else 1)
oracle = sys.argv[1:2] == ['--oracle']
if oracle and len(sys.argv) != 4:
    raise SystemExit('usage: patch-radv-wsi.py --oracle PINNED_MESA_ROOT OUTPUT_ROOT')
original_root = Path(sys.argv[2]) if oracle else root.parent/'mihawk-mesa-review'
output_root = Path(sys.argv[3]) if oracle else root.parent/'mihawk-vulkan-review/.deps/work/radv-src'
source = original_root/'src/vulkan/wsi/wsi_common_videoout.c'
target = output_root/'src/vulkan/wsi/wsi_common_videoout.c'
text = source.read_text()

def replace(old, new):
    global text
    assert text.count(old) == 1, f'Pinned WSI anchor changed: {old[:70]}'
    text = text.replace(old, new)

replace('   bool opened;\n', '   unsigned owners;\n   bool closing, stop, registered;\n   int64_t physical;\n   bool opened;\n')
replace('   .handle = -1,', '   .handle = -1,\n   .physical = -1,')
replace('static int\nsceVideoOutSetFlipRate', 'static int\nsceVideoOutClose(int32_t handle)\n{\n   return 0;\n}\n\nstatic int\nsceVideoOutSetFlipRate')
replace('   if (out->buffers)\n      return VK_SUCCESS;',
        '   if (out->buffers)\n      return out->registered ? VK_SUCCESS : VK_ERROR_INITIALIZATION_FAILED;')
replace('   buffers = address;', '   buffers = address;\n   out->physical = physical;')
replace('   int result = sceVideoOutSetFlipRate',
        '   /* Track partial registration too: final-owner cleanup must release it. */\n   out->buffers = buffers;\n   int result = sceVideoOutSetFlipRate')
replace('   out->buffers = buffers;\n   return VK_SUCCESS;',
        '   out->registered = true;\n   return VK_SUCCESS;')
replace('      while (out->queue_count == 0)\n         cnd_wait(&out->changed, &out->lock);',
        '      while (out->queue_count == 0 && !out->stop)\n         cnd_wait(&out->changed, &out->lock);\n      if (out->queue_count == 0 && out->stop) {\n         mtx_unlock(&out->lock);\n         return 0;\n      }')
replace('VkResult\nwsi_display_init_wsi',
        (root/'tools/radv-videoout-lifecycle.inc').read_text()+'\nVkResult\nwsi_display_init_wsi')
# 120 Hz: the app asks for it per game session (headless/display_refresh.h). The pinned source
# decides from the package's param.json, which the app cannot read once it has left the sandbox,
# and for the whole run; the package declares the capability (tools/package-headless-native.sh).
replace('''   FILE *const file = fopen("/app0/sce_sys/param.json", "rb");
   if (file == NULL)
      return false;
   char text[16384];
   const size_t length = fread(text, 1, sizeof(text) - 1, file);
   fclose(file);
   text[length] = '\\0';
   const char *at = strstr(text, "\\"attribute3\\"");
   if (at == NULL || (at = strchr(at, ':')) == NULL)
      return false;
   const unsigned long value = strtoul(at + 1, NULL, 0);
   return (value & VIDEOOUT_ATTRIBUTE3_HIGH_FRAME_RATE) == VIDEOOUT_ATTRIBUTE3_HIGH_FRAME_RATE;
''', '''   const char *const asked = getenv("EDEN_VIDEOOUT_120HZ");
   return asked != NULL && asked[0] == '1';
''')
# From upstream ProsperoEden 1f7fcf36 (#95): VRR screens can report a 48Hz
# vblank during idle while their 120Hz output is valid. Only a measured
# stable 59.94/60Hz fallback (15–18.5ms vblank) justifies reverting 120Hz.
# This only runs when high refresh is requested and the TV supports it.
replace('         if (period > VIDEOOUT_HIGH_REFRESH_LIMIT_NS) {',
        '         if (period > UINT64_C(15000000) && period < UINT64_C(18500000)) {')
# Say so when the display follows, as the pinned source does when it does not.
replace('''                    (double)period / 1e6);
         }
      } else {''', '''                    (double)period / 1e6);
         } else {
            fprintf(stderr, "wsi/videoout: 119.88 Hz output, a vblank every %.3f ms\\n", (double)period / 1e6);
         }
      } else {''')
replace('   wsi->base.get_support =', '   videoout_ref();\n\n   wsi->base.get_support =')
replace('   if (wsi)\n      vk_free(alloc, wsi);',
        '   if (wsi) {\n      videoout_unref();\n      vk_free(alloc, wsi);\n      wsi_device->wsi[VK_ICD_WSI_PLATFORM_DISPLAY] = NULL;\n   }')
changed = not target.exists() or target.read_text() != text
if changed:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    # Upstream caches the whole build by pin. Invalidate only that receipt;
    # Ninja retains all unchanged objects and rebuilds the patched WSI.
    provenance = root.parent/'mihawk-vulkan-review/.deps/native/radv-release/PROVENANCE.txt'
    if not oracle and provenance.exists():
        provenance.replace(provenance.with_suffix('.base.txt'))
print(f'RADV WSI adaptation changed={changed} sha256={hashlib.sha256(text.encode()).hexdigest()}')

# Preserve the reason behind RADV's successful-but-empty device enumeration.
# These startup-only diagnostics avoid repeated full game runs for each stage.
for relative, replacements in {
    # Restore the pinned upload path: explicit CPU flush did not affect HUD corruption.
    'src/amd/vulkan/radv_cmd_buffer.c': [
        # Mesa 26.2.4 (2026-10-01), upstream 1f4f4aeee9db552e2955db77ee5584aa729b0644:
        # Use the actual height, not the already clamped width, for GFX10 bin size.
        ('   extent.height = MAX2(extent.width, pdev->info.gfx_level >= GFX12 ? 128 : 64);',
         '   extent.height = MAX2(extent.height, pdev->info.gfx_level >= GFX12 ? 128 : 64);'),
    ],
    'src/amd/vulkan/radv_pipeline.c': [
        # Mesa 26.2.2 (2026-09-02), upstream 3261364cab95877988e0bcf767e5f68c03f35652
        # The TRUNC_COORD sampler bit must not change array-layer rounding.
        ('''               .lower_array_layer_round_even =
                  !compiler_info->ac->conformant_trunc_coord && !compiler_info->key.disable_trunc_coord,''',
         '''               .lower_array_layer_round_even = !compiler_info->ac->conformant_trunc_coord,'''),
    ],
    'src/amd/vulkan/meta/radv_meta_clear.c': [
        # Official Mesa 26.2.4 upstream 2752b54feeed5bb6fc7d21982b4c8acab0d0e613
        ("      if (ds_att->format == VK_FORMAT_UNDEFINED)\n         return;\n\n      VkClearDepthStencilValue clear_value", "      if (ds_att->format == VK_FORMAT_UNDEFINED)\n         return;\n\n      /* Vulkan dynamic rendering: ignore missing depth/stencil aspects. */\n      aspects &= render->ds_att_aspects;\n      if (!aspects)\n         return;\n\n      VkClearDepthStencilValue clear_value"),
        ("radv_fast_clear_depth(cmd_buffer, ds_att->iview, clear_att->clearValue.depthStencil, clear_att->aspectMask,", "radv_fast_clear_depth(cmd_buffer, ds_att->iview, clear_att->clearValue.depthStencil, aspects,"),
        ("emit_depthstencil_clear(cmd_buffer, clear_att->clearValue.depthStencil, clear_att->aspectMask, clear_rect,", "emit_depthstencil_clear(cmd_buffer, clear_att->clearValue.depthStencil, aspects, clear_rect,"),
    ],
    'src/amd/vulkan/meta/radv_meta_resolve.c': [
        # Official Mesa 26.2.4 upstream 6e18409d5800f975538236c4152fa4eeca3b444e
        ("      const struct radv_image_view *src_iview = d_iview ? d_iview : s_iview;\n\n      const VkImageSubresourceLayers subresource", "      const struct radv_image_view *src_iview = d_iview ? d_iview : s_iview;\n      VkImageAspectFlags ds_att_aspects;\n      if (d_iview && s_iview) {\n         ds_att_aspects = VK_IMAGE_ASPECT_DEPTH_BIT | VK_IMAGE_ASPECT_STENCIL_BIT;\n      } else if (d_iview) {\n         ds_att_aspects = VK_IMAGE_ASPECT_DEPTH_BIT;\n      } else {\n         ds_att_aspects = VK_IMAGE_ASPECT_STENCIL_BIT;\n      }\n\n\n      const VkImageSubresourceLayers subresource"),
        ("      struct radv_image_view *src_iview = d_iview ? d_iview : s_iview;\n      struct radv_image_view *dst_iview = d_res_iview ? d_res_iview : s_res_iview;", "      VkImageAspectFlags ds_att_aspects;\n      if (d_iview && s_iview) {\n         ds_att_aspects = VK_IMAGE_ASPECT_DEPTH_BIT | VK_IMAGE_ASPECT_STENCIL_BIT;\n      } else if (d_iview) {\n         ds_att_aspects = VK_IMAGE_ASPECT_DEPTH_BIT;\n      } else {\n         ds_att_aspects = VK_IMAGE_ASPECT_STENCIL_BIT;\n      }\n\n      struct radv_image_view *src_iview = d_iview ? d_iview : s_iview;\n      struct radv_image_view *dst_iview = d_res_iview ? d_res_iview : s_res_iview;"),
        (".aspectMask = src_iview->vk.aspects,", ".aspectMask = ds_att_aspects,"),
        (".aspectMask = dst_iview->vk.aspects,", ".aspectMask = ds_att_aspects,"),
    ],
    'src/amd/vulkan/radv_physical_device.c': [
        ('   if (result == VK_ERROR_INCOMPATIBLE_DRIVER || result == VK_ERROR_INITIALIZATION_FAILED)\n      return VK_SUCCESS;',
         '   if (result != VK_SUCCESS) fprintf(stderr, "radv/ps5: physical device creation result=%d\\n", result);\n   if (result == VK_ERROR_INCOMPATIBLE_DRIVER || result == VK_ERROR_INITIALIZATION_FAILED)\n      return VK_SUCCESS;'),
        ('   if (!pdev->addrlib) {', '   if (!pdev->addrlib) {\n      fprintf(stderr, "radv/ps5: addrlib creation failed\\n");'),
    ],
    'src/amd/vulkan/winsys/ps5/radv_ps5_winsys.c': [
        ('   if (!radv_ps5_platform_init())\n      return;', '   if (!radv_ps5_platform_init()) {\n      fprintf(stderr, "radv/ps5: queue platform initialization failed\\n");\n      return;\n   }'),
        ('   if (!radv_ps5_memory_alloc(RADV_PS5_RING_BYTES, RADV_PS5_LARGE_BYTES, true, &queue->ring))\n      return;', '   if (!radv_ps5_memory_alloc(RADV_PS5_RING_BYTES, RADV_PS5_LARGE_BYTES, true, &queue->ring)) {\n      fprintf(stderr, "radv/ps5: queue ring allocation failed\\n");\n      return;\n   }'),
        ('      radv_ps5_memory_free(&queue->ring);', '      fprintf(stderr, "radv/ps5: queue marker allocation failed\\n");\n      radv_ps5_memory_free(&queue->ring);'),
    ],
    'src/amd/vulkan/winsys/ps5/radv_ps5_platform.c': [
        ("   radv_ps5_submit_ns[0] += flushed - started;", "   p_atomic_add(&radv_ps5_submit_ns[0], flushed - started);"),
        ("   radv_ps5_submit_ns[1] += submitted - flushed;", "   p_atomic_add(&radv_ps5_submit_ns[1], submitted - flushed);"),
        ("#include <time.h>\n", "#include <time.h>\n#include <stdatomic.h>\n"),
        ("static bool radv_ps5_kick_pending;", "static atomic_bool radv_ps5_kick_pending = ATOMIC_VAR_INIT(false);"),
        ("while (!radv_ps5_kick_pending)", "while (!atomic_load_explicit(&radv_ps5_kick_pending, memory_order_acquire))"),
        ("      radv_ps5_kick_pending = false;", "      atomic_store_explicit(&radv_ps5_kick_pending, false, memory_order_release);"),
        ("   mtx_lock(&radv_ps5_kick_lock);\n   radv_ps5_kick_pending = true;\n   cnd_signal(&radv_ps5_kick_wanted);\n   mtx_unlock(&radv_ps5_kick_lock);", "   // A wake is already scheduled when pending was true. Do not take the\n   // producer mutex and signal the condition variable for every additional\n   // DCB in the same GPU kick batch: FC27 submits thousands per window.\n   // Only the thread changing false->true signals; the consumer clears\n   // pending before suspend, so later submissions always get another kick.\n   if (!atomic_exchange_explicit(&radv_ps5_kick_pending, true, memory_order_acq_rel)) {\n      mtx_lock(&radv_ps5_kick_lock);\n      cnd_signal(&radv_ps5_kick_wanted);\n      mtx_unlock(&radv_ps5_kick_lock);\n   }"),
        ('''bool
radv_ps5_memory_grant_gpu(void *address, uint64_t bytes)
{
   /* A title's anonymous memory takes GPU access this way, and a shader then
    * writes it through the CPU's address (HARDWARE_FINDINGS.md, 2026-09-27). */
   return sceKernelMprotect(address, bytes,
                            PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE | PS5_KERNEL_PROT_GPU_READ |
                               PS5_KERNEL_PROT_GPU_WRITE) == 0;
}''', (root/'tools/radv-host-memory.inc').read_text().strip()),
        ('   if (!placed) {', '   if (!placed) {\n      fprintf(stderr, "radv/ps5: mapping rejected result=%d address=%p bytes=%llu window32=%d\\n", result, address, (unsigned long long)bytes, window32);'),
    ],
}.items():
    original = original_root/relative
    destination = output_root/relative
    adapted = original.read_text()
    for old, new in replacements:
        # Mesa 26.2.4 resolves one depth/stencil image in both decompression
        # and resolve paths. Both identical source masks must be corrected.
        expected = 2 if (relative == 'src/amd/vulkan/meta/radv_meta_resolve.c'
                         and old == '.aspectMask = src_iview->vk.aspects,') else 1
        assert adapted.count(old) == expected, f'Pinned initialization anchor changed: {relative}'
        adapted = adapted.replace(old, new)
    if relative == 'src/amd/vulkan/radv_cmd_buffer.c':
        # Official Mesa 26.2.2 zero-draw firmware workaround, adapted to our
        # PS5 GS-compute raster path without bypassing any real draw packet.
        from radv_official_indirect_draw_fix import patch as patch_zero_indirect_draw
        adapted = patch_zero_indirect_draw(adapted)
    if not destination.exists() or destination.read_text() != adapted:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(adapted)
        provenance = root.parent/'mihawk-vulkan-review/.deps/native/radv-release/PROVENANCE.txt'
        if not oracle and provenance.exists():
            provenance.replace(provenance.with_suffix('.base.txt'))
    print(f'RADV initialization diagnostic {relative} sha256={hashlib.sha256(adapted.encode()).hexdigest()}')
