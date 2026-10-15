# Vertex input identity correction — 16 October 2026

Historical shader-classification code used only the vertex-B hash when choosing
whether the current graphics pipeline may use static input with no vertex
attributes. Merged vertex programs depend on both vertex-A and vertex-B.
Two distinct vertex-A programs with the same vertex-B could otherwise inherit
the wrong classification. The maintained fork now uses the exact A/B identity
array, as corrected in reference upstream change #184.

The GPU pipeline cache destructor also resets its process-global last-bound
vertex-input hint, preventing a previous game's state from skipping new
vertex buffer dirty rebinding. The per-title development reset restores
static_vertex_input=true before the next title's per-session switches.

Both source-generator and active versioned Vulkan files are updated together.
The host regression compiles the extracted actual classification helper with
Clang address/UB sanitizers to check colliding B hashes, cache invalidation
and two independent title resets. It is not a rendering-on-console test.

No console build, release or hardware test. Existing FC27 image/HUD errors
might have other causes; do not label them fixed from host checks.

Reference: https://github.com/blackbearreloaded/ProsperoEden/commit/1b6ffb88727d3ea079666d53b4d8cdf3c069dba3
