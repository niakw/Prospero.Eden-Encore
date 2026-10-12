#!/usr/bin/env python3
"""Pinned original Mesa 26.2.0 -> Mesa 26.2.4 immutable sampler ownership.
Reference: https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa/+/7b5888e8ca77cc0b407c7fb113df85764b561a86
"""
C_EDITS = [
  [
    "   const size_t size = sizeof(struct radv_descriptor_update_template) +\n                       sizeof(struct radv_descriptor_update_template_entry) * entry_count;\n",
    ""
  ],
  [
    "   struct radv_descriptor_update_template *templ;\n   uint32_t i;",
    "   struct radv_descriptor_update_template *templ;\n   uint32_t immutable_sampler_count = 0;\n   uint8_t *immutable_samplers_data;\n   uint32_t i;"
  ],
  [
    "   templ = vk_alloc2(&device->vk.alloc, pAllocator, size, 8, VK_SYSTEM_ALLOCATION_SCOPE_OBJECT);\n   if (!templ)\n      return vk_error(device, VK_ERROR_OUT_OF_HOST_MEMORY);\n\n   vk_object_base_init(&device->vk, &templ->base, VK_OBJECT_TYPE_DESCRIPTOR_UPDATE_TEMPLATE);\n\n   templ->entry_count = entry_count;\n\n",
    ""
  ],
  [
    "      templ->bind_point = pCreateInfo->pipelineBindPoint;\n",
    ""
  ],
  [
    "      set_layout = radv_descriptor_set_layout_from_handle(pCreateInfo->descriptorSetLayout);\n   }\n\n   for (i = 0; i < entry_count; i++) {",
    "      set_layout = radv_descriptor_set_layout_from_handle(pCreateInfo->descriptorSetLayout);\n   }\n\n   /* Official Mesa 26.2.4: templates own immutable sampler descriptor bytes. */\n   if (pCreateInfo->templateType == VK_DESCRIPTOR_UPDATE_TEMPLATE_TYPE_PUSH_DESCRIPTORS_KHR) {\n      for (i = 0; i < entry_count; i++) {\n         const VkDescriptorUpdateTemplateEntry *entry = &pCreateInfo->pDescriptorUpdateEntries[i];\n         const struct radv_descriptor_set_binding_layout *binding_layout = set_layout->binding + entry->dstBinding;\n         if ((entry->descriptorType == VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER ||\n              entry->descriptorType == VK_DESCRIPTOR_TYPE_SAMPLER) &&\n             binding_layout->immutable_samplers_offset)\n            immutable_sampler_count += entry->descriptorCount;\n      }\n   }\n\n   const size_t size = sizeof(struct radv_descriptor_update_template) +\n                       sizeof(struct radv_descriptor_update_template_entry) * entry_count +\n                       (size_t)immutable_sampler_count * RADV_SAMPLER_DESC_SIZE;\n   templ = vk_alloc2(&device->vk.alloc, pAllocator, size, 8, VK_SYSTEM_ALLOCATION_SCOPE_OBJECT);\n   if (!templ)\n      return vk_error(device, VK_ERROR_OUT_OF_HOST_MEMORY);\n   vk_object_base_init(&device->vk, &templ->base, VK_OBJECT_TYPE_DESCRIPTOR_UPDATE_TEMPLATE);\n   templ->entry_count = entry_count;\n   templ->bind_point = pCreateInfo->pipelineBindPoint;\n   immutable_samplers_data = (uint8_t *)&templ->entry[entry_count];\n\n   for (i = 0; i < entry_count; i++) {"
  ],
  [
    "      const uint32_t *immutable_samplers = NULL;",
    "      const uint8_t *immutable_samplers = NULL;"
  ],
  [
    "               immutable_samplers = radv_immutable_samplers(set_layout, binding_layout) + entry->dstArrayElement * 4;",
    "               const uint32_t *src_samplers =\n                  radv_immutable_samplers(set_layout, binding_layout) + entry->dstArrayElement * 4;\n               memcpy(immutable_samplers_data, src_samplers, entry->descriptorCount * RADV_SAMPLER_DESC_SIZE);\n               immutable_samplers = immutable_samplers_data;\n               immutable_samplers_data += entry->descriptorCount * RADV_SAMPLER_DESC_SIZE;"
  ],
  [
    "templ->entry[i].immutable_samplers + 4 * j",
    "templ->entry[i].immutable_samplers + RADV_SAMPLER_DESC_SIZE * j",
    2
  ]
]
H_EDITS = [
  [
    "   const uint32_t *immutable_samplers;",
    "   const uint8_t *immutable_samplers;"
  ]
]

def _apply(src, edits, name):
    for old, new, *occurrences in edits:
        count = occurrences[0] if occurrences else 1
        if src.count(old) != count:
            raise RuntimeError(f"{name}: unexpected pinned input for {old[:100]!r}")
        src = src.replace(old, new)
    return src

def patch_c(src):
    return _apply(src, C_EDITS, "template.c")

def patch_h(src):
    return _apply(src, H_EDITS, "template.h")
