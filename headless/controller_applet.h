// SPDX-License-Identifier: GPL-3.0-or-later
// The guest controller applet (a game's "connect controllers" screen) without a UI. Eden's default
// connects only the game's minimum player count, which disconnects a second player whenever a game
// asks; this connects one player per PS5 controller in use, within the game's limits, with the
// same controller style priority (Pro Controller, dual Joy-Con, single Joy-Con, handheld).
#pragma once
#include <algorithm>
#include <array>
#include <bit>
#include <cstdio>
#include <optional>
#include "common/settings.h"
#include "core/frontend/applets/controller.h"
#include "devices.h"
#include "diagnostics.h"
#include "hid_core/frontend/emulated_controller.h"
#include "hid_core/hid_core.h"

namespace Eden {
// The controller a player gets for what the game allows: a Pro Controller, else a Joy-Con pair,
// else single Joy-Cons (a left one for players 1 and 3 and a right one for 2 and 4 when the game
// takes both), else handheld for player 1. A handheld-only title still gets Handheld even when the
// emulated console is Docked: returning no controller can leave the title waiting forever.
// If the title names no style at all, try a Pro Controller so the applet always answers.
inline std::optional<Core::HID::NpadStyleIndex> ControllerStyle(
    const Core::Frontend::ControllerParameters& parameters, std::size_t index) {
    using Core::HID::NpadStyleIndex;
    if (parameters.allow_pro_controller) return NpadStyleIndex::Fullkey;
    if (parameters.allow_dual_joycons) return NpadStyleIndex::JoyconDual;
    if (parameters.allow_left_joycon && parameters.allow_right_joycon)
        return index % 2 == 0 ? NpadStyleIndex::JoyconLeft : NpadStyleIndex::JoyconRight;
    if (parameters.allow_left_joycon) return NpadStyleIndex::JoyconLeft;
    if (parameters.allow_right_joycon) return NpadStyleIndex::JoyconRight;
    if (parameters.allow_handheld)
        return index == 0 ? std::optional{NpadStyleIndex::Handheld} : std::nullopt;
    return NpadStyleIndex::Fullkey;
}

class PadControllerApplet final : public Core::Frontend::ControllerApplet {
public:
    PadControllerApplet(Core::HID::HIDCore& hid_core_, const Pad& pad_) : hid_core{hid_core_}, pad{pad_} {}

    void Close() const override {}

    void ReconfigureControllers(ReconfigureCallback callback,
                                const Core::Frontend::ControllerParameters& parameters) const override {
        const std::size_t min_players =
            parameters.enable_single_mode ? 1 : std::max<std::size_t>(std::max<int>(parameters.min_players, 1), 1);
        const std::size_t max_players =
            parameters.enable_single_mode ? 1 : std::max<std::size_t>(std::max<int>(parameters.max_players, 1), min_players);
        const std::size_t pads = std::popcount(pad.ConnectedPlayers() | 1u);
        const std::size_t players = std::clamp(pads, min_players, max_players);
        const bool docked = ::Settings::IsDockedMode();
        std::size_t connected = 0;

        // Preserve already-connected compatible controllers when the guest explicitly asks us
        // to. This mirrors Eden #4420 while still targeting one emulated player per connected PS5
        // pad. The old PS5 applet disconnected/reconnected every pad unconditionally.
        using Core::HID::NpadStyleIndex;
        std::array<bool, Core::HID::HIDCore::available_controllers> keep_connected{};
        for (std::size_t index = 0;
             index < Core::HID::HIDCore::available_controllers - 1 && connected < players; ++index) {
            const auto* controller = hid_core.GetEmulatedControllerByIndex(index);
            if (!parameters.keep_controllers_connected || !controller->IsConnected()) continue;
            const auto style = controller->GetNpadStyleIndex();
            keep_connected[index] =
                (style == NpadStyleIndex::Fullkey && parameters.allow_pro_controller) ||
                (style == NpadStyleIndex::JoyconDual && parameters.allow_dual_joycons) ||
                (style == NpadStyleIndex::JoyconLeft && parameters.allow_left_joycon) ||
                (style == NpadStyleIndex::JoyconRight && parameters.allow_right_joycon) ||
                (style == NpadStyleIndex::Handheld && parameters.allow_handheld) ||
                (style == NpadStyleIndex::GameCube && parameters.allow_gamecube_controller);
            connected += keep_connected[index] ? 1u : 0u;
        }

        auto* handheld = hid_core.GetEmulatedController(Core::HID::NpadIdType::Handheld);
        if (!keep_connected[Core::HID::HIDCore::available_controllers - 2] && handheld->IsConnected())
            handheld->Disconnect();

        for (std::size_t index = 0; index < Core::HID::HIDCore::available_controllers - 2; ++index) {
            auto* controller = hid_core.GetEmulatedControllerByIndex(index);
            if (keep_connected[index]) continue;
            if (controller->IsConnected()) controller->Disconnect();
            if (connected >= players) continue;
            const auto style = ControllerStyle(parameters, index);
            if (!style) continue;
            controller->SetNpadStyleIndex(*style);
            controller->Connect(true);
            ++connected;
        }

        // A handheld-only title has no numbered pad slot. Keep the existing Encore fallback so a
        // docked PS5 does not leave that guest waiting forever for a controller style it requires.
        if (connected == 0 && players == 1 && parameters.allow_handheld) {
            handheld->SetNpadStyleIndex(NpadStyleIndex::Handheld);
            handheld->Connect(true);
            connected = 1;
        }
        // What the game asked for goes to the log: a game stuck on this screen can then be told
        // apart from one that asks for a controller this port does not provide.
        char line[224];
        std::snprintf(line, sizeof(line),
                      "Game asks for %d to %d players (single mode %d); takes pro=%d pair=%d left=%d right=%d "
                      "handheld=%d; %s, %zu PS5 controller(s): connected %zu",
                      parameters.min_players, parameters.max_players, parameters.enable_single_mode,
                      parameters.allow_pro_controller, parameters.allow_dual_joycons, parameters.allow_left_joycon,
                      parameters.allow_right_joycon, parameters.allow_handheld, docked ? "docked" : "handheld",
                      pads, connected);
        Report("controllers", line);
        if (connected == 0)
            Report("controllers", "No additional controller can be connected for this request");
        callback(true);
    }

private:
    Core::HID::HIDCore& hid_core;
    const Pad& pad;
};
}
