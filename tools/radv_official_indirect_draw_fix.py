#!/usr/bin/env python3
"""Mesa official 26.2.2 a2f2518a: skip zero-length indirect GPU draw packets.

Source upstream: https://github.com/mirror/mesa/commit/a2f2518a9febf1b3b791cd2df079dbd25e56939b
The pinned PS5 RADV adds one GS-compute raster caller, adapted with a count
of one for its generated indirect packet. Fail closed on source drift.
"""

def patch(source: str) -> str:
    def once(haystack: str, before: str, after: str) -> str:
        assert haystack.count(before) == 1, f"Missing/ambiguous Mesa anchor: {before[:100]}"
        return haystack.replace(before, after)

    source = once(source,
        "radv_before_draw(struct radv_cmd_buffer *cmd_buffer, const struct radv_draw_info *info, uint32_t drawCount, bool dgc)",
        "radv_before_draw(struct radv_cmd_buffer *cmd_buffer, const struct radv_draw_info *info, uint32_t drawCount,\n                 uint32_t max_indirect_draw_count, bool dgc)")
    source = once(source,
        """      if (unlikely(!info->count && !info->strmout_va))
         return false;
   }

   if (!info->indexed""",
        """      if (unlikely(!info->count && !info->strmout_va))
         return false;
   } else {
      // The AMD firmware may execute the first indirect draw even with count=0.
      // Ported from official RADV a2f2518a (2026-08-31).
      if (!max_indirect_draw_count)
         return false;
   }

   if (!info->indexed""")

    # Change exactly one call inside each complete function, avoiding broad
    # string replaces that could corrupt another draw path.
    targets = [
        ("radv_gs_compute_rasterize", "radv_before_draw(cmd_buffer, &rast, 1, false)",
         "radv_before_draw(cmd_buffer, &rast, 1, direct ? 0 : 1, false)"),
        ("radv_CmdDraw", "radv_before_draw(cmd_buffer, &info, 1, false)",
         "radv_before_draw(cmd_buffer, &info, 1, 0, false)"),
        ("radv_CmdDrawMultiEXT", "radv_before_draw(cmd_buffer, &info, drawCount, false)",
         "radv_before_draw(cmd_buffer, &info, drawCount, 0, false)"),
        ("radv_CmdDrawIndexed", "radv_before_draw(cmd_buffer, &info, 1, false)",
         "radv_before_draw(cmd_buffer, &info, 1, 0, false)"),
        ("radv_CmdDrawMultiIndexedEXT", "radv_before_draw(cmd_buffer, &info, drawCount, false)",
         "radv_before_draw(cmd_buffer, &info, drawCount, 0, false)"),
        ("radv_CmdDrawIndirect2KHR", "radv_before_draw(cmd_buffer, &info, 1, false)",
         "radv_before_draw(cmd_buffer, &info, 1, pInfo->drawCount, false)"),
        ("radv_CmdDrawIndexedIndirect2KHR", "radv_before_draw(cmd_buffer, &info, 1, false)",
         "radv_before_draw(cmd_buffer, &info, 1, pInfo->drawCount, false)"),
        ("radv_CmdDrawIndirectCount2KHR", "radv_before_draw(cmd_buffer, &info, 1, false)",
         "radv_before_draw(cmd_buffer, &info, 1, pInfo->maxDrawCount, false)"),
        ("radv_CmdDrawIndexedIndirectCount2KHR", "radv_before_draw(cmd_buffer, &info, 1, false)",
         "radv_before_draw(cmd_buffer, &info, 1, pInfo->maxDrawCount, false)"),
        ("radv_CmdExecuteGeneratedCommandsEXT", "radv_before_draw(cmd_buffer, &info, 1, true)",
         "radv_before_draw(cmd_buffer, &info, 1, layout->vk.draw_count ? pGeneratedCommandsInfo->maxDrawCount : 1,\n                               true)"),
        ("radv_CmdDrawIndirectByteCount2EXT", "radv_before_draw(cmd_buffer, &info, 1, false)",
         "radv_before_draw(cmd_buffer, &info, 1, 0, false)"),
    ]
    for function, old, new in targets:
        token = "\n" + function + "("
        assert source.count(token) == 1, f"Cannot locate function {function}"
        a = source.index(token)
        b = source.index("\n}\n", a) + len("\n}\n")
        original = source[a:b]
        updated = once(original, old, new)
        source = source[:a] + updated + source[b:]
    assert source.count("radv_before_draw(") == 12
    assert source.count("radv_before_draw(cmd_buffer, &info, 1, false)") == 0
    return source
