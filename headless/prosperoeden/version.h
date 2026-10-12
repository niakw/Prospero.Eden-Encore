// SPDX-License-Identifier: GPL-3.0-or-later
// Encore has its own user-facing release line. The PS5 contentVersion remains numeric because
// sce_sys/param.json requires that format.
#pragma once

namespace Eden {
// Keep the separately versioned public package metadata stable.
// The launcher footer uses the EXACT R-label supplied by CMake at build time.
inline constexpr const char* kAppVersion = "R1";
#ifdef EDEN_LAUNCHER_BUILD_LABEL
inline constexpr const char* kBuildVersion = EDEN_LAUNCHER_BUILD_LABEL;
#else
inline constexpr const char* kBuildVersion = kAppVersion;
#endif
inline constexpr const char* kPackageVersion = "01.000.041";
}
