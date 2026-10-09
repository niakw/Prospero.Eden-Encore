// SPDX-License-Identifier: GPL-3.0-or-later
#include "pe/ui/launcher.hpp"

#include <algorithm>
#include <string>

namespace pe::ui
{
using audio::Cue;

namespace
{
constexpr Rect kDialog{550.0f, 180.0f, 820.0f, 720.0f};
constexpr float kRowsTop = 334.0f;
constexpr float kRowPitch = 96.0f;
constexpr float kRowHeight = 94.0f;
constexpr int kRowsShown = 5;
constexpr Rect kWindow{592.0f, kRowsTop, 736.0f, kRowPitch * (kRowsShown - 1) + kRowHeight};
constexpr float kHints = 848.0f;

constexpr const char* kGameLabels[kGameButtons] = {
    "A", "B", "X", "Y", "L", "R", "ZL", "ZR", "+", "-", TR("Left stick press"), TR("Right stick press")};
constexpr const char* kPadLabels[kPadButtons] = {
    TR("Cross"), TR("Circle"), TR("Square"), TR("Triangle"), "L1", "R1", "L2", "R2",
    "L3", "R3", TR("Options"), TR("Create"), TR("Touchpad")};

Pad physical_pad_icon(int pad)
{
    static constexpr Pad icons[kPadButtons] = {
        Pad::cross, Pad::circle, Pad::square, Pad::triangle, Pad::l1, Pad::r1, Pad::l2,
        Pad::r2, Pad::l3, Pad::r3, Pad::options, Pad::create, Pad::touchpad};
    return icons[static_cast<std::size_t>(std::clamp(pad, 0, kPadButtons - 1))];
}

std::string profile_name(int layout, const ButtonMapping& mapping)
{
    const bool custom = mapping_is_custom(mapping, layout);
    if (layout == 1)
        return custom ? tr("Custom Switch") : tr("Switch");
    return custom ? tr("Custom PS5") : tr("PlayStation");
}
}

void Launcher::open_mapping(bool for_game)
{
    mapping_for_game_ = for_game;
    mapping_rows_.visible = kRowsShown;
    mapping_rows_.pitch = kRowPitch;
    mapping_rows_.reset(kGameButtons, 0);
    modal_ = modal_shown_ = Modal::mapping;
    message_.clear();
    cue(Cue::open);
}

void Launcher::press_mapping(Key key)
{
    if (key != Key::square)
        clear_confirmation();
    // Exactly the same prelaunch resolution policy used by main.cpp.
    const ButtonMapping effective = mapping_for_game_ ?
        ResolveSessionButtonMapping(prefs_.controller_layout, prefs_.mapping,
            game_settings_.controller_layout, game_settings_.own_mapping,
            game_settings_.mapping).buttons : prefs_.mapping;
    ButtonMapping mapping = effective;
    const int row = std::clamp(mapping_rows_.selected, 0, kGameButtons - 1);

    if (key == Key::circle)
    {
        modal_ = modal_shown_ = mapping_for_game_ ? Modal::game : Modal::controls;
        option_ = mapping_for_game_ ? 9 : 1;
        option_cursor_.snap(dialog_row_top(modal_, option_));
        message_.clear();
        cue(Cue::back);
        return;
    }
    if (key == Key::up || key == Key::down)
    {
        if (mapping_rows_.move(key == Key::down ? 1 : -1))
        {
            message_.clear();
            cue(Cue::focus);
        }
        return;
    }

    bool reset = key == Key::square;
    if (!reset && key != Key::left && key != Key::right && key != Key::cross)
        return;
    if (reset && !confirm_action(Confirmation::mapping_reset))
        return;

    if (!reset)
    {
        const int step = key == Key::left ? -1 : 1;
        const int pad = (mapping[static_cast<std::size_t>(row)] + step + kPadButtons) % kPadButtons;
        mapping = assign_button(mapping, row, pad);
    }

    bool saved = false;
    if (mapping_for_game_)
    {
        GameSettings next = game_settings_;
        if (reset)
        {
            next.own_mapping = false;
            next.controller_layout = -1;
            next.mapping = base_mapping_for_layout(prefs_.controller_layout);
        }
        else
        {
            next.own_mapping = true;
            if (next.controller_layout < 0)
                next.controller_layout = prefs_.controller_layout;
            next.mapping = mapping;
        }
        if (!games_.empty())
            saved = services_.set_game_settings(games_[static_cast<std::size_t>(library_.selected)].title_id, next);
        if (saved) game_settings_ = next;
        say(saved ? (reset ? tr("Button mapping reset to global settings.") :
                             tr("Saved for this game. Applies on next launch.")) :
                    tr("Could not save. Please try again."), !saved);
    }
    else
    {
        const Preferences before = prefs_;
        prefs_.mapping = reset ? base_mapping_for_layout(prefs_.controller_layout) : mapping;
        saved = save_preferences(true);
        if (!saved) prefs_ = before;
        if (saved)
            say(reset ? tr("Button mapping reset to the active profile.") : tr("Button mapping saved."));
    }
    cue(saved ? Cue::toggle : Cue::error);
}

void Launcher::draw_mapping(Canvas& c, float open)
{
    gfx::DrawList& list = c.list;
    list.push_opacity(open);
    list.push_transform(1.0f - 0.03f * (1.0f - open) * motion(), 960.0f, 540.0f, 0.0f,
                        (1.0f - open) * 26.0f * motion());
    glass(c, kDialog, 26.0f, theme::kPanel.with_alpha(0.97f), theme::kPanelEdge.with_alpha(0.66f), 1.6f);
    text_shrink(c, tr("Button mapping"), 592.0f, baseline(218.0f, 62.0f, theme::kDisplay),
                theme::kDisplay, theme::kTitle, 736.0f);

    const Game* game = mapping_for_game_ && !games_.empty() ?
        &games_[static_cast<std::size_t>(library_.selected)] : nullptr;
    const int effective_layout =
        mapping_for_game_ && game_settings_.controller_layout >= 0 ?
            game_settings_.controller_layout : prefs_.controller_layout;
    const ButtonMapping mapping = mapping_for_game_ ?
        ResolveSessionButtonMapping(prefs_.controller_layout, prefs_.mapping,
            game_settings_.controller_layout, game_settings_.own_mapping,
            game_settings_.mapping).buttons : prefs_.mapping;
    const std::string active_profile = profile_name(effective_layout, mapping);
    const std::string subtitle = game ?
        game->name + " · " +
            (game_settings_.own_mapping ? active_profile :
                                         fill(tr("Global ({0})"), {active_profile})) :
        fill(tr("Global controller profile: {0}"), {active_profile});
    text_fit(c, subtitle, 592.0f, baseline(291.0f, 32.0f, theme::kSmall),
             theme::kSmall, theme::kCopy, 736.0f);

    list.push_clip({kWindow.x - 24.0f, kWindow.y - 6.0f, kWindow.w + 48.0f, kWindow.h + 12.0f});
    const auto row_top = [&](int row) {
        return kRowsTop + static_cast<float>(row) * kRowPitch - mapping_rows_.scroll();
    };
    for (int row = mapping_rows_.first_row(); row <= mapping_rows_.last_row(); ++row)
    {
        list.push_opacity(mapping_rows_.row_alpha(row, kRowHeight));
        plate_rest(c, kRowPlate, {592.0f, row_top(row), 736.0f, kRowHeight});
        list.pop_opacity();
    }
    plate_focus(c, kRowPlate,
                {592.0f, kRowsTop + mapping_rows_.cursor() - mapping_rows_.scroll(), 736.0f, kRowHeight},
                1.0f);

    for (int row = mapping_rows_.first_row(); row <= mapping_rows_.last_row(); ++row)
    {
        const float top = row_top(row);
        const int pad = mapping[static_cast<std::size_t>(row)];
        const ButtonMapping& base = base_mapping_for_layout(effective_layout);
        const bool usual = pad == base[static_cast<std::size_t>(row)];
        list.push_opacity(mapping_rows_.row_alpha(row, kRowHeight));
        const float value_baseline = baseline(top, kRowHeight, theme::kText24);
        const float taken = chooser(c, tr(kPadLabels[std::clamp(pad, 0, kPadButtons - 1)]), 1296.0f,
                                    value_baseline, row == mapping_rows_.selected ? 1.0f : 0.0f,
                                    usual ? theme::kLimePale : theme::kLime);
        // Do not make players translate a controller button name in their head: the actual PS5
        // glyph is shown beside the textual label, including shoulders, sticks and touchpad.
        const float icon_size = 28.0f;
        const Pad icon = physical_pad_icon(pad);
        const float icon_w = pad_width(icon, icon_size);
        draw_pad(c, icon, 1296.0f - taken - icon_w - 10.0f, top + kRowHeight * 0.5f, icon_size);
        text_shrink(c, tr(kGameLabels[row]), 628.0f, value_baseline, theme::kText24, theme::kValue,
                    664.0f - taken - icon_w - 42.0f);
        list.pop_opacity();
    }
    list.pop_clip();
    scrollbar(c, mapping_rows_, 1340.0f, kWindow.y, kWindow.h);

    if (!message_.empty())
    {
        notice_block(c, message_, 592.0f, kHints - 6.0f, theme::kSmall, 26.0f,
                     message_warning_ ? theme::kWarning : theme::kLimePale, 736.0f, 2, message_warning_);
    }
    else
    {
        static constexpr Hint kHintsRow[] = {
            {Pad::updown, TR("Select")}, {Pad::leftright, TR("Change")},
            {Pad::square, TR("Reset")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kHintsRow, 4, 592.0f, kHints, theme::kCopy, 736.0f);
    }

    list.pop_transform();
    list.pop_opacity();
}

} // namespace pe::ui

