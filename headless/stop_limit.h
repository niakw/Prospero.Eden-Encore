// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <chrono>
#include <string>

namespace Eden::StopLimit {
inline constexpr std::chrono::seconds kLimit{10};

// Starts one process-lifetime watcher after elevation/startup is complete.
void Start(std::string note) noexcept;
// Arm when the player/session has asked to stop the current game.
void Begin() noexcept;
// Disarm once no game is being torn down.
void End() noexcept;
} // namespace Eden::StopLimit
