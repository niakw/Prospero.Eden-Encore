// ProsperoEden - OpenGL backend for the 2D draw list.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/gfx/gl_batch.hpp"

#include "pe/gfx/gl_program.hpp"

#include <algorithm>
#include <cmath>

namespace pe::gfx
{

namespace
{

constexpr const char *kVertex = R"(
layout(location = 0) in vec4 a_rect;
layout(location = 1) in vec4 a_top;
layout(location = 2) in vec4 a_bottom;
layout(location = 3) in vec4 a_border;
layout(location = 4) in vec4 a_params;
layout(location = 5) in vec4 a_extra;
layout(location = 0) uniform vec4 u_viewport; // scale, offset x, offset y
layout(location = 1) uniform vec2 u_surface;
out vec2 v_local;
out vec2 v_virtual;
out vec2 v_uv;
out vec2 v_st;
flat out vec2 v_half;
flat out vec4 v_top;
flat out vec4 v_bottom;
flat out vec4 v_border;
flat out vec4 v_params;
flat out vec4 v_extra;
const vec2 kCorners[6] = vec2[6](vec2(0.0, 0.0), vec2(1.0, 0.0), vec2(0.0, 1.0),
                                 vec2(1.0, 0.0), vec2(1.0, 1.0), vec2(0.0, 1.0));
void main()
{
    vec2 corner = kCorners[gl_VertexID];
    int shape = int(a_params.w + 0.5);
    vec2 size = a_rect.zw;
    // Grow shapes by their softness plus one output pixel for anti-aliasing;
    // glyph and image quads map texels exactly and are not grown.
    float pad = (shape == 1 || shape == 3 || shape == 9 || shape == 10 || shape == 11 || shape == 12 || shape == 13 || shape == 14 || shape == 15) ?
        0.0 : a_params.z + 1.0 / u_viewport.x;
    vec2 local = mix(vec2(-pad), size + vec2(pad), corner);
    vec2 virt = a_rect.xy + local;
    vec2 unit = local / max(size, vec2(1e-3));
    v_virtual = virt;
    v_local = local - 0.5 * size;
    v_half = 0.5 * size;
    v_st = clamp(unit, 0.0, 1.0);
    v_uv = mix(a_extra.xy, a_extra.zw, unit);
    v_top = a_top;
    v_bottom = a_bottom;
    v_border = a_border;
    v_params = a_params;
    v_extra = a_extra;
    float clip_w = 1.0;
    if (shape == 9 || shape == 10 || shape == 11 || shape == 12 || shape == 13 || shape == 14 || shape == 15) {
        // A real projective quad, not a horizontally squashed 2D image.
        // Shared retail-case geometry across all titles and console/host.
        const float a = a_params.x;
        const float cs = cos(a), sn = sin(a);
        const vec2 centre = a_rect.xy + 0.5 * size;
        const vec2 local = (corner - 0.5) * size;
        float x, z;
        if (shape == 9 || shape == 11) {
            // Place a real back surface on the FAR plane of the case.
            // It must not occupy the same Z as the front artwork.
            float depth = a_params.y > 0.5 ? 44.0 : 0.0;
            x = local.x * cs - depth * sn;
            z = -local.x * sn - depth * cs;
            vec2 oriented = vec2(a_params.y > 0.5 ? 1.0 - corner.x : corner.x,
                                 corner.y);
            v_uv = mix(a_extra.xy, a_extra.zw, oriented);
        } else if (shape == 10 || shape == 14 || shape == 15) {
            // The side lies between two parallel printed planes. It occupies
            // real space in Z rather than being a 2D strip in screen-space.
            float side = a_extra.x < -0.5 ? -0.5 :
                         a_extra.x > 0.5 ? 0.5 :
                         (sn > 0.0 ? -0.5 : 0.5);
            float edge_x = side * size.x;
            float depth = a_params.z + corner.x * a_params.y;
            x = edge_x * cs - depth * sn;
            z = -edge_x * sn - depth * cs;
            if (shape == 14) v_uv = vec2(corner.x, corner.y);
        } else if (shape == 12) {
            float depth = corner.y * a_params.z;
            x = local.x * cs - depth * sn;
            z = -local.x * sn - depth * cs;
        } else {
            // True rounded corner: eight 3D quarter-arc segments, extruded
            // along the full case depth. This is an actual curved silhouette,
            // NOT a 2D rounded border or a flat image on the side.
            const float pi = 3.14159265358979323846;
            int quadrant = int(a_extra.x + 0.5);
            float theta0 = quadrant == 0 ? pi :
                           quadrant == 1 ? 1.5*pi :
                           quadrant == 2 ? 0.0 : 0.5*pi;
            float theta = theta0 +
                (a_extra.y + corner.y) / max(1.0, a_extra.z) * 0.5*pi;
            float radius = a_params.y;
            float side_x = (quadrant == 0 || quadrant == 3 ? -1.0 : 1.0);
            float side_y = (quadrant <= 1 ? -1.0 : 1.0);
            float rounded_x = side_x * (0.5 * size.x - radius) +
                              radius * cos(theta);
            float rounded_y = side_y * (0.5 * size.y - radius) +
                              radius * sin(theta);
            float depth = corner.x * a_params.z;
            x = rounded_x * cs - depth * sn;
            z = -rounded_x * sn - depth * cs;
            // Normal on curved side, consumed by the lit plastic material.
            v_uv = vec2(cos(theta), sin(theta));
            virt.y = rounded_y;
        }
        // One rigid transform for all six surfaces. Previously the caps
        // faked a separate vertical slope, leaving visibly disconnected
        // white triangles at the plastic corners.
        float world_y = shape == 12 ?
            (a_params.y > 0.5 ? 0.5 : -0.5) * size.y :
            shape == 13 ? virt.y : local.y;
        const float pitch = 0.055;
        float pitched_y = world_y * cos(pitch) - z * sin(pitch);
        float pitched_z = world_y * sin(pitch) + z * cos(pitch);
        clip_w = max(0.65, 1.0 - pitched_z / 820.0);
        // Small camera roll exposes the shell while preserving the paper's
        // perspective (and retaining the same camera for front/back/corners).
        virt = centre + vec2(x + pitched_y * 0.018,
                             pitched_y + x * 0.045) / clip_w;
        v_virtual = virt;
    }
    vec2 surface = virt * u_viewport.x + u_viewport.yz;
    vec2 ndc = surface / u_surface * 2.0 - 1.0;
    // Non-unit W gives hardware perspective-correct image UV interpolation.
    gl_Position = vec4(ndc.x * clip_w, -ndc.y * clip_w, 0.0, clip_w);
}
)";

constexpr const char *kFragment = R"(
layout(location = 0) uniform vec4 u_viewport;
layout(location = 2) uniform sampler2D u_texture;
in vec2 v_local;
in vec2 v_virtual;
in vec2 v_uv;
in vec2 v_st;
flat in vec2 v_half;
flat in vec4 v_top;
flat in vec4 v_bottom;
flat in vec4 v_border;
flat in vec4 v_params;
flat in vec4 v_extra;
out vec4 frag_color;

float round_box(vec2 p, vec2 b, float r)
{
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

float triangle(vec2 p, vec2 p0, vec2 p1, vec2 p2)
{
    vec2 e0 = p1 - p0, e1 = p2 - p1, e2 = p0 - p2;
    vec2 v0 = p - p0, v1 = p - p1, v2 = p - p2;
    vec2 q0 = v0 - e0 * clamp(dot(v0, e0) / dot(e0, e0), 0.0, 1.0);
    vec2 q1 = v1 - e1 * clamp(dot(v1, e1) / dot(e1, e1), 0.0, 1.0);
    vec2 q2 = v2 - e2 * clamp(dot(v2, e2) / dot(e2, e2), 0.0, 1.0);
    float s = sign(e0.x * e2.y - e0.y * e2.x);
    vec2 d = min(min(vec2(dot(q0, q0), s * (v0.x * e0.y - v0.y * e0.x)),
                     vec2(dot(q1, q1), s * (v1.x * e1.y - v1.y * e1.x))),
                 vec2(dot(q2, q2), s * (v2.x * e2.y - v2.y * e2.x)));
    return -sqrt(d.x) * sign(d.y);
}

void main()
{
    float px = 1.0 / u_viewport.x; // virtual units per output pixel
    int shape = int(v_params.w + 0.5);
    vec4 fill = mix(v_top, v_bottom, shape == 7 ? v_st.x : v_st.y);
    vec4 color;
    if (shape == 0 || shape == 7)
    {
        float radius = min(v_params.x, min(v_half.x, v_half.y));
        float d = round_box(v_local, v_half, radius);
        color = fill;
        if (v_params.y > 0.0)
        {
            float inner = clamp(0.5 - (d + v_params.y) / px, 0.0, 1.0);
            color = mix(v_border, fill, inner);
        }
        color.a *= clamp(0.5 - d / px, 0.0, 1.0);
    }
    else if (shape == 1)
    {
        float sdf = texture(u_texture, v_uv).r;
        float distance = (sdf - 0.5) * 2.0 * v_params.x + v_params.y;
        color = vec4(fill.rgb, fill.a * clamp(distance / px + 0.5, 0.0, 1.0));
    }
    else if (shape == 2)
    {
        float radius = min(v_params.x, min(v_half.x, v_half.y));
        float d = round_box(v_local, v_half, radius);
        color = vec4(fill.rgb, fill.a * (1.0 - smoothstep(-v_params.z, v_params.z, d)));
    }
    else if (shape == 3)
    {
        color = texture(u_texture, v_uv) * fill;
    }
    else if (shape == 9)
    {
        // The paper is a square-cornered continuous wrap, not three
        // individually rounded rectangles separated from the side print.
        float d = round_box(v_local, v_half, 0.0);
        color = v_params.z > 0.5 ? texture(u_texture, clamp(v_uv, 0.0, 1.0)) * v_top : v_top;
        float scan_inside = v_params.z > 0.5 ?
            step(0.0, v_uv.x) * step(v_uv.x, 1.0) *
            step(0.0, v_uv.y) * step(v_uv.y, 1.0) : 1.0;
        color.a *= scan_inside * (1.0 - smoothstep(-1.0, 1.0, d));
    }
    else if (shape == 14)
    {
        // A flat original scan is texture-mapped onto our own dimensional
        // side plane. The scan carries ink only, not any 3D shell pixels.
        vec4 ink = texture(u_texture, v_uv);
        float side_light = 0.81 + 0.19 * (1.0 - v_st.x);
        color = vec4(ink.rgb * v_top.rgb * side_light, ink.a * v_top.a);
    }
    else if (shape == 15)
    {
        // User's red empty-spine reference rendered as clean vector features
        // directly on our physical side plane. No low-resolution texture or
        // fake game title is ever stretched to cover the height.
        vec2 p = vec2(v_st.x * 44.0, v_st.y * 730.0);
        vec3 red = v_top.rgb * (0.85 + 0.15 * (1.0 - v_st.x));
        float left_outer = 1.0 - smoothstep(-0.9, 0.9,
            round_box(p - vec2(14.5, 34.0), vec2(8.0, 20.0), 7.7));
        float left_inner = 1.0 - smoothstep(-0.9, 0.9,
            round_box(p - vec2(14.5, 34.0), vec2(5.1, 17.0), 5.0));
        float right_body = 1.0 - smoothstep(-0.9, 0.9,
            round_box(p - vec2(30.0, 34.0), vec2(7.8, 20.0), 7.5));
        float left_dot = 1.0 - smoothstep(2.3, 3.9,
            length(p - vec2(14.5, 25.5)));
        float right_dot = 1.0 - smoothstep(2.3, 3.9,
            length(p - vec2(30.0, 42.0)));
        float footer = 1.0 - smoothstep(-0.8, 0.8,
            round_box(p - vec2(22.0, 683.0), vec2(12.0, 26.0), 9.0));
        float footer_inset = 1.0 - smoothstep(-0.8, 0.8,
            round_box(p - vec2(22.0, 683.0), vec2(8.7, 22.0), 6.0));
        float symbol = max(max(left_outer - left_inner, right_body),
                           max(left_dot, footer - footer_inset));
        vec3 white = vec3(0.96, 0.97, 1.0);
        vec3 ink = mix(red, white, clamp(symbol, 0.0, 1.0));
        ink = mix(ink, red, right_dot * 0.92);
        color = vec4(ink, v_top.a);
    }
    else if (shape == 10)
    {
        // An inked side wall, not a red overlay on a flat poster. Near/far
        // planes receive different light; a narrow front-facing lip catches
        // the rim light without turning the whole wall bright white.
        float rim = exp(-70.0 * min(v_st.x, 1.0 - v_st.x));
        float broad = 0.77 + 0.20 * (1.0 - v_st.x);
        color = mix(v_top, v_bottom, v_st.x);
        color.rgb = min(vec3(1.0), color.rgb * broad +
            vec3(0.44, 0.34, 0.36) * rim * 0.18);
    }
    else if (shape == 12)
    {
        // Rounded top/bottom plastic cap: half-transparent near rim, brighter
        // distal reflection, subdued middle to retain physical depth.
        // Solid top/bottom surfaces: diffused light in the plastic, distinct
        // bright front-edge refraction, and a darker rear-facing inner wall.
        float front_glint = exp(-48.0 * v_st.y);
        float rear_shadow = smoothstep(0.58, 1.0, v_st.y);
        float near_edge = smoothstep(0.0, 0.02, v_st.x) *
                          smoothstep(0.0, 0.02, 1.0 - v_st.x);
        color = mix(v_top, v_bottom, v_st.y);
        color.rgb = min(vec3(1.0), color.rgb * (0.96 - 0.24 * rear_shadow) +
                        vec3(0.17, 0.19, 0.22) * front_glint);
        color.a *= near_edge * (0.86 + 0.10 * front_glint);
    }
    else if (shape == 13)
    {
        // Soft plastic with a curved normal-derived highlight and an
        // illuminated front rim, darkening naturally toward the rear plane.
        vec2 n = normalize(v_uv);
        vec2 key_light = normalize(vec2(-0.58, -0.82));
        vec2 secondary = normalize(vec2(0.92, -0.39));
        float diffuse = 0.48 + 0.37 * max(dot(n, key_light), 0.0);
        float highlight = pow(max(dot(n, key_light), 0.0), 20.0);
        float fill = 0.11 * max(dot(n, secondary), 0.0);
        // Curved corner normals interpolate across eight physical strips.
        // The highlight tracks their actual curvature, not a screen border.
        float near_glint = 0.20 * exp(-20.0 * v_st.x);
        float rear_shadow = 1.0 - 0.23 * v_st.x;
        vec4 material = mix(v_top, v_bottom, v_st.x);
        material.rgb = min(vec3(1.0), material.rgb *
            (diffuse + fill + near_glint) * rear_shadow +
            vec3(0.62, 0.72, 0.83) * highlight * 0.41);
        material.a *= 0.90 - 0.15 * v_st.x;
        color = material;
    }
    else if (shape == 11)
    {
        // One molded shell around the SAME paper, projected on its face.
        // Only the 12px RIGHT opening, 13px TOP and 13px BOTTOM are lit.
        // The rest is fully transparent, never a second overlay on the ink.
        float from_edge = (1.0 - v_st.x) * (v_half.x * 2.0);
        float from_cap = min(v_st.y, 1.0 - v_st.y) * (v_half.y * 2.0);
        float bevel = 1.0 - smoothstep(8.0, 13.0, from_edge);
        float outer_glint = exp(-0.5 * pow((from_edge - 2.3) / 1.25, 2.0));
        float inner_ridge = exp(-0.5 * pow((from_edge - 9.0) / 1.55, 2.0));
        float grazing = 0.15 + 0.20 * pow(abs(sin(v_params.x)), 1.5);
        // A visible molded front/rear cap line even when the horizontal
        // depth surface projects almost edge-on (especially at the bottom).
        float cap_band = 1.0 - smoothstep(11.5, 13.2, from_cap);
        float cap_outer = exp(-0.5 * pow((from_cap - 1.8) / 1.25, 2.0));
        float cap_inner = exp(-0.5 * pow((from_cap - 11.5) / 1.6, 2.0));
        float cap_sheen = 0.78 + 0.22 * cos(v_st.x * 5.8 + v_params.x);
        float cap_intensity = (0.53 * cap_band + 0.30 * cap_outer +
                               0.25 * cap_inner) * cap_sheen;
        float rim_intensity = (0.27 + grazing) * bevel +
                              0.44 * outer_glint + 0.22 * inner_ridge;
        // Fine manufacturing grain on PLASTIC ONLY, never on the scan.
        float grain = 0.96 + 0.04 * sin(v_st.y * 670.0);
        float sheen = 0.5 + 0.5 * sin(v_st.y * 7.0 + v_params.x * 0.65);
        vec3 material = mix(v_top.rgb, vec3(0.99, 0.995, 1.0),
                            0.29 + 0.19 * sheen);
        float shell = 1.0 - smoothstep(-1.0, 1.0,
                            round_box(v_local, v_half, 22.0));
        color = vec4(material, v_top.a * shell *
                     clamp(max(rim_intensity, cap_intensity) * grain,
                           0.0, 0.96));
    }
    else if (shape == 8)
    {
        float radius = min(v_params.x, min(v_half.x, v_half.y));
        float d = round_box(v_local, v_half, radius);
        color = texture(u_texture, v_uv) * fill;
        color.a *= clamp(0.5 - d / px, 0.0, 1.0);
    }
    else if (shape == 4)
    {
        vec2 pa = v_virtual - v_extra.xy;
        vec2 ba = v_extra.zw - v_extra.xy;
        float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
        float d = length(pa - ba * h) - 0.5 * v_params.y;
        color = vec4(fill.rgb, fill.a * clamp(0.5 - d / px, 0.0, 1.0));
    }
    else
    {
        float d = triangle(v_local, vec2(0.0, -v_half.y), vec2(-v_half.x, v_half.y),
                           vec2(v_half.x, v_half.y));
        if (v_params.y > 0.0)
            d = abs(d + 0.5 * v_params.y) - 0.5 * v_params.y;
        color = vec4(fill.rgb, fill.a * clamp(0.5 - d / px, 0.0, 1.0));
    }
    if (color.a <= 0.0)
        discard;
    frag_color = color;
}
)";

} // namespace

GlBatch::~GlBatch()
{
    release();
}

void GlBatch::release()
{
    glDeleteBuffers(static_cast<GLsizei>(buffers_.size()), buffers_.data());
    glDeleteVertexArrays(static_cast<GLsizei>(vaos_.size()), vaos_.data());
    if (program_ != 0)
        glDeleteProgram(program_);
    buffers_.fill(0);
    vaos_.fill(0);
    capacities_.fill(0);
    next_slot_ = 0;
    program_ = 0;
}

bool GlBatch::init()
{
    program_ = build_program("batch2d", kVertex, kFragment);
    if (program_ == 0)
        return false;
    glGenVertexArrays(static_cast<GLsizei>(vaos_.size()), vaos_.data());
    glGenBuffers(static_cast<GLsizei>(buffers_.size()), buffers_.data());
    constexpr GLsizei stride = sizeof(Instance);
    // Each VAO remembers its own VBO. Rotating both prevents a stalled
    // read of the previous frame's same-size storage in the PS5 GL driver.
    for (std::size_t slot = 0; slot < buffers_.size(); ++slot)
    {
        glBindVertexArray(vaos_[slot]);
        glBindBuffer(GL_ARRAY_BUFFER, buffers_[slot]);
        for (GLuint attribute = 0; attribute < 6; ++attribute)
        {
            glEnableVertexAttribArray(attribute);
            glVertexAttribPointer(
                attribute, 4, GL_FLOAT, GL_FALSE, stride,
                reinterpret_cast<const void *>(static_cast<std::uintptr_t>(attribute * 16)));
            glVertexAttribDivisor(attribute, 1);
        }
    }
    glBindVertexArray(0);
    glBindBuffer(GL_ARRAY_BUFFER, 0);
    return true;
}

std::uint32_t GlBatch::create_font_texture(const Font &font)
{
    GLuint texture = 0;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_R8, font.atlas_width(), font.atlas_height(), 0, GL_RED,
                 GL_UNSIGNED_BYTE, font.atlas().data());
    // One level only: mip chains leave ps5-opengl's batched fast path.
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL, 0);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    return texture;
}

void GlBatch::sync_font_texture(std::uint32_t texture, const Font &font)
{
    int first = 0;
    int last = 0;
    if (texture == 0 || !font.take_changed_rows(&first, &last))
        return;
    glBindTexture(GL_TEXTURE_2D, texture);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, first, font.atlas_width(), last - first, GL_RED, GL_UNSIGNED_BYTE,
                    font.atlas().data() + static_cast<std::size_t>(first) * font.atlas_width());
}

std::uint32_t GlBatch::create_texture(int width, int height, const std::uint8_t *rgba)
{
    GLuint texture = 0;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL, 0);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    return texture;
}

void GlBatch::delete_texture(std::uint32_t texture)
{
    if (texture != 0)
        glDeleteTextures(1, &texture);
}

void GlBatch::draw(const DrawList &list, const Viewport &viewport, int surface_width,
                   int surface_height)
{
    draw_calls_ = 0;
    const auto &instances = list.instances();
    if (instances.empty())
        return;
    // The old path orphaned the SAME GL store every frame. PS5 OpenGL can
    // drain on that operation, making held-D-pad navigation stutter.
    // Rotate three VBOs, and resize a store only when it actually grows.
    const std::size_t slot = next_slot_++ % kStreamBufferSlots;
    glBindBuffer(GL_ARRAY_BUFFER, buffers_[slot]);
    const auto capacity = StreamCapacity(capacities_[slot], instances.size());
    if (capacity != capacities_[slot])
    {
        glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(capacity * sizeof(Instance)), nullptr,
                     GL_STREAM_DRAW);
        capacities_[slot] = capacity;
    }
    glBufferSubData(GL_ARRAY_BUFFER, 0,
                    static_cast<GLsizeiptr>(instances.size() * sizeof(Instance)),
                    instances.data());

    glViewport(0, 0, surface_width, surface_height);
    glEnable(GL_BLEND);
    glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glUseProgram(program_);
    glUniform4f(0, viewport.scale, viewport.offset_x, viewport.offset_y, 0.0f);
    glUniform2f(1, static_cast<float>(surface_width), static_cast<float>(surface_height));
    glUniform1i(2, 0);
    glActiveTexture(GL_TEXTURE0);

    GLuint bound_texture = 0;
    bool scissor = false;
    Rect last_scissor_clip{};
    glBindVertexArray(vaos_[slot]);
    for (const Run &run : list.runs())
    {
        if (run.count == 0)
            continue;
        if (run.texture != 0 && run.texture != bound_texture)
        {
            glBindTexture(GL_TEXTURE_2D, run.texture);
            bound_texture = run.texture;
        }
        if (run.clipped)
        {
            // Runs with different textures often share the same clip. Keep
            // the actual last GL scissor and avoid recomputing/submitting it
            // for every image/text run in a clipped library panel.
            const bool new_scissor =
                !scissor || run.clip.x != last_scissor_clip.x ||
                run.clip.y != last_scissor_clip.y ||
                run.clip.w != last_scissor_clip.w ||
                run.clip.h != last_scissor_clip.h;
            if (!scissor)
                glEnable(GL_SCISSOR_TEST);
            scissor = true;
            if (new_scissor)
            {
                const float x0 = std::floor(run.clip.x * viewport.scale + viewport.offset_x);
                const float y0 = std::floor(run.clip.y * viewport.scale + viewport.offset_y);
                const float x1 =
                    std::ceil((run.clip.x + run.clip.w) * viewport.scale + viewport.offset_x);
                const float y1 =
                    std::ceil((run.clip.y + run.clip.h) * viewport.scale + viewport.offset_y);
                glScissor(static_cast<GLint>(x0), surface_height - static_cast<GLint>(y1),
                          static_cast<GLsizei>(std::max(0.0f, x1 - x0)),
                          static_cast<GLsizei>(std::max(0.0f, y1 - y0)));
                last_scissor_clip = run.clip;
            }
        }
        else if (scissor)
        {
            glDisable(GL_SCISSOR_TEST);
            scissor = false;
        }
        glDrawArraysInstancedBaseInstance(GL_TRIANGLES, 0, 6, static_cast<GLsizei>(run.count),
                                          run.first);
        ++draw_calls_;
    }
    if (scissor)
        glDisable(GL_SCISSOR_TEST);
    glBindVertexArray(0);
}

} // namespace pe::gfx
