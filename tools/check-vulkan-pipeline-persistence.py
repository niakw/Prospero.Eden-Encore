#!/usr/bin/env python3
"""Source contracts for PS5 foreground Vulkan pipeline caching.

Do not cancel the persistent compiler worker pool while initializing a title's
disk cache. This checks integration only; runtime PS5 result is not proven.
"""
import ast
from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=(root/"headless/main.cpp").read_text()
port=(root/"tools/prepare-vulkan-port.py").read_text()
ast.parse(port)
assert 'Settings::values.use_disk_shader_cache = game;' in main
assert 'Settings::values.use_vulkan_driver_pipeline_cache = game;' in main
assert '#ifdef EDEN_PS5_VULKAN\n                if (game && Settings::values.use_disk_shader_cache.GetValue())' in main
assert 'lazy_cache.request_stop();' in main
assert 'LoadDiskResources(\n                            title_id, lazy_cache.get_token(),' in main
assert 'EDEN_VULKAN_SHADER_CACHE title=' in main
assert 'if shader_source.count(lazy_vulkan_cache_anchor) != 1:' in port
assert 'if (stop_loading.stop_requested()) {' in port
assert 'LOG_INFO(Render_Vulkan, "PS5 lazy shader cache ready' in port
assert port.index('if (stop_loading.stop_requested()) {') < port.index('shader_source = shader_source.replace(lazy_vulkan_cache_anchor')
# An early return only after pipeline filenames and driver cache creation,
# before emitting any queue/wait/cancel commands: the worker pool survives.
v=port.split("lazy_vulkan_cache_replacement = '''",1)[1].split("'''",1)[0]
assert v.index('LoadVulkanPipelineCache(') < v.index('if (stop_loading.stop_requested())')
assert v.index('if (stop_loading.stop_requested())') < v.index('    struct {')
assert 'workers.WaitForRequests' not in v
print("PASS Vulkan PS5 lazy shader cache lifecycle and non-destructive persistent worker pool")
print("Driver cache / filesystem correctness on real PS5: NOT TESTED")
