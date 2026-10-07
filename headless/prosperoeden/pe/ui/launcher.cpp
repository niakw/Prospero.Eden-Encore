// ProsperoEden - The launcher: home, library, settings and their dialogs.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/launcher.hpp"

#include <algorithm>

namespace pe::ui
{

using audio::Cue;

namespace
{

constexpr Rect kScreen{0.0f, 0.0f, 1920.0f, 1080.0f};
const Color kWhite{1.0f, 1.0f, 1.0f, 1.0f};

} // namespace

Launcher::Launcher(Services &services, Textures &textures, const Fonts &fonts, bool first_start)
    : services_(services), textures_(textures), fonts_(fonts), first_start_(first_start)
{
    version_ = services_.version();
    clock_ = services_.clock();
    prefs_ = services_.preferences();
    apply_look();
    read_home();
    refresh_home_hero();
    const bool continue_ready = home_.setup_ready && home_.last_exists;
    home_focus_ = continue_ready ? 0 : home_.setup_ready ? 1 : 2;
    home_springs_[static_cast<std::size_t>(home_focus_)].snap(1.0f);
    settings_.visible = 7;
    settings_.pitch = 88.0f;
    settings_.reset(7, 0);
    section_.snap(1.0f);
    detail_.snap(1.0f);
    cue(home_.launch_failed ? Cue::notify : first_start ? Cue::welcome : Cue::resume);
    start_scan();
}

Launcher::~Launcher()
{
    // The game list may still be reading; it uses the services this launcher was given.
    if (scan_.valid())
        scan_.wait();
    if (media_scan_.valid())
        media_scan_.wait();
}

std::vector<Cue> Launcher::take_cues()
{
    std::vector<Cue> result;
    result.swap(cues_);
    return result;
}

void Launcher::say(const std::string &text, bool warning)
{
    message_ = text;
    message_warning_ = warning;
    message_age_ = 0.0f;
}

void Launcher::clear_confirmation()
{
    confirmation_ = Confirmation::none;
}

bool Launcher::confirm_action(Confirmation action)
{
    if (confirmation_ != action)
    {
        confirmation_ = action;
        confirmation_key_ = pressed_key_;
        const char *question = TR("Confirm this action?");
        switch (action)
        {
        case Confirmation::restore_defaults: question = TR("Restore default settings?"); break;
        case Confirmation::game_overrides: question = TR("Reset this game's custom settings?"); break;
        case Confirmation::mapping_reset: question = TR("Reset controller mapping?"); break;
        case Confirmation::shader_caches: question = TR("Clear shader/JIT caches?"); break;
        case Confirmation::console_mode: question = TR("Change console mode for this game?"); break;
        default: break;
        }
        say(tr(question), true);
        cue(Cue::notify);
        return false;
    }
    clear_confirmation();
    message_.clear();
    return true;
}

void Launcher::open(Screen screen, bool forward)
{
    leaving_ = screen_;
    screen_ = screen;
    forward_ = forward;
    transition_.start(theme::kScreenSeconds);
    message_.clear();
    clear_confirmation();
    cue(forward ? Cue::open : Cue::back);
}

void Launcher::open_modal(Modal modal)
{
    modal_ = modal_shown_ = modal;
    option_ = 0;
    option_cursor_.snap(dialog_row_top(modal, 0));
    message_.clear();
    clear_confirmation();
    // Switches show their state at once; they only animate when changed.
    const std::array<bool, 3> states = switch_states(modal);
    for (std::size_t i = 0; i < states.size(); ++i)
        switches_[i].snap(states[i] ? 1.0f : 0.0f);
    cue(Cue::modal_open);
}

std::array<bool, 3> Launcher::switch_states(Modal modal) const
{
    switch (modal)
    {
    case Modal::video:
        return {prefs_.hud, false, false};
    case Modal::audio:
        return {prefs_.mute, false, false};
    case Modal::controls:
        return {false, prefs_.vibration, false};
    case Modal::accessibility:
        return {prefs_.large_text, prefs_.high_contrast, prefs_.reduce_motion};
    default:
        return {prefs_.detailed_logging, false, false};
    }
}

void Launcher::close_modal()
{
    modal_ = Modal::none;
    message_.clear();
    clear_confirmation();
    cue(Cue::modal_close);
}

void Launcher::apply_look()
{
    look() = {prefs_.large_text, prefs_.high_contrast, prefs_.reduce_motion};
}

bool Launcher::save_preferences(bool quiet)
{
    const bool saved = services_.set_preferences(prefs_);
    if (!saved)
        say(tr("Could not save settings. Please try again."), true);
    else if (quiet)
        message_.clear();
    else
        say(tr("Saved. Applies when a game starts."));
    return saved;
}

void Launcher::launch(const std::string &file, const std::string &title, const std::string &cover)
{
    if (!services_.game_exists(file))
    {
        read_home();
        drop_missing_games();
        say(tr("ROM missing from the game files folder"), true);
        cue(Cue::error);
        return;
    }
    selected_game_ = services_.game_path(file);
    launch_title_ = title;
    launch_cover_ = cover;
    launch_.start(theme::kLaunchSeconds);
    press_ = 1.0f;
    cue(Cue::launch);
}

void Launcher::press(Key key)
{
    if (!selected_game_.empty())
        return; // a game is starting
    // Confirmation is a real modal: Circle cancels, Cross confirms. Other buttons cannot leak
    // through to the underlying screen while the dialog is visible.
    if (confirmation_ != Confirmation::none)
    {
        if (key == Key::circle)
        {
            clear_confirmation();
            message_.clear();
            cue(Cue::back);
            return;
        }
        if (key == Key::cross)
            key = confirmation_key_;
        else
        {
            cue(Cue::error);
            return;
        }
    }
    pressed_key_ = key;
    if (modal_ == Modal::game)
        return press_game(key);
    if (modal_ == Modal::mods)
        return press_mods(key);
    if (modal_ == Modal::mapping)
        return press_mapping(key);
    if (modal_ != Modal::none)
        return press_dialog(key);
    switch (screen_)
    {
    case Screen::home:
        return press_home(key);
    case Screen::library:
        return press_library(key);
    case Screen::settings:
        return press_settings(key);
    case Screen::files:
        return press_files(key);
    case Screen::language:
        return press_language(key);
    case Screen::about:
        if (key == Key::circle)
            open(Screen::home, false);
        return;
    }
}

void Launcher::update(float dt)
{
    time_ += dt;
    intro_ += dt;
    message_age_ += dt;
    backdrop_.update(dt);
    textures_.pump(dt);
    finish_scan(false);
    finish_selected_media();
    update_controllers(dt);
    transition_.update(dt);
    press_ = std::max(0.0f, press_ - dt / 0.18f);

    modal_open_.target = modal_ != Modal::none ? 1.0f : 0.0f;
    modal_open_.update(dt, 20.0f);
    if (modal_ == Modal::none && modal_open_.value < 0.01f)
        modal_shown_ = Modal::none;
    dim_.target = screen_ == Screen::home ? 0.0f : 0.30f;
    dim_.update(dt, 8.0f);

    for (std::size_t i = 0; i < home_springs_.size(); ++i)
    {
        home_springs_[i].target = static_cast<int>(i) == home_focus_ ? 1.0f : 0.0f;
        home_springs_[i].update(dt, theme::kFocusSpring);
    }
    library_.update(dt);
    settings_.update(dt);
    files_.update(dt);
    language_.update(dt);
    video_rows_.update(dt);
    game_rows_.update(dt);
    mod_rows_.update(dt);
    mapping_rows_.update(dt);
    mode_.target = selected_docked_ ? 0.0f : 1.0f;
    mode_.update(dt, 22.0f);
    const bool mods_on = library_.selected >= 0 && library_.selected < static_cast<int>(games_.size()) &&
                         games_[static_cast<std::size_t>(library_.selected)].mods_enabled;
    mods_switch_.target = mods_on ? 1.0f : 0.0f;
    mods_switch_.update(dt, 22.0f);
    detail_.target = 1.0f;
    detail_.update(dt, 14.0f);
    section_.target = 1.0f;
    section_.update(dt, 14.0f);
    if (modal_ != Modal::none && modal_ != Modal::mapping)
        option_cursor_.target = dialog_row_top(modal_, option_);
    option_cursor_.update(dt, theme::kCursorSpring);
    const std::array<bool, 3> states = switch_states(modal_shown_);
    for (std::size_t i = 0; i < states.size(); ++i)
    {
        switches_[i].target = states[i] ? 1.0f : 0.0f;
        switches_[i].update(dt, 22.0f);
    }

    presence_wait_ += dt;
    if (presence_wait_ >= 2.0f && selected_game_.empty())
    {
        presence_wait_ = 0.0f;
        check_games_present();
    }

    clock_wait_ += dt;
    if (clock_wait_ >= 1.0f)
    {
        clock_wait_ = 0.0f;
        clock_ = services_.clock();
    }

    if (!selected_game_.empty())
    {
        launch_.update(dt);
        if (!launch_.running)
            done_ = true;
    }
}

void Launcher::draw_screen(Canvas &c, Screen screen)
{
    switch (screen)
    {
    case Screen::home:
        return draw_home(c);
    case Screen::library:
        return draw_library(c);
    case Screen::settings:
        return draw_settings(c);
    case Screen::files:
        return draw_files(c);
    case Screen::language:
        return draw_language(c);
    case Screen::about:
        return draw_about(c);
    }
}

void Launcher::draw_top_nav(Canvas &c, int active_tab, int focus_tab, float focus_amount)
{
    auto& list = c.list;
    if (textures_.brand() != 0)
        list.rounded_image(textures_.brand(), {72.0f, 28.0f, 84.0f, 84.0f},
                           {0.0f, 0.0f, 1.0f, 1.0f}, 18.0f, kWhite);
    text(c, "EDEN", 176.0f, baseline(43.0f, 35.0f, theme::kText24), theme::kText24,
         theme::kTitle, Align::left, 3.0f);
    text(c, "ENCORE", 176.0f, baseline(77.0f, 24.0f, theme::kSmall), theme::kSmall,
         theme::kLime, Align::left, 5.0f);

    static constexpr const char* labels[] = {TR("Home"), TR("Library"), TR("RECENTLY PLAYED"), TR("Settings")};
    static constexpr float xs[] = {720.0f, 886.0f, 1046.0f, 1260.0f};
    static constexpr float widths[] = {154.0f, 148.0f, 202.0f, 160.0f};
    for (int i = 0; i < 4; ++i)
    {
        const Rect r{xs[i], 44.0f, widths[i], 54.0f};
        const bool active = i == active_tab;
        const float focused = i == focus_tab ? tween::clamp01(focus_amount) : 0.0f;
        if (active)
        {
            // Persistent section state: restrained pill + underline. Controller focus is the
            // brighter animated glow, so selected and hovered can never be confused.
            list.bordered_rect(r, 22.0f, theme::kPanel.with_alpha(0.34f), 1.0f,
                               theme::kPanelEdge.with_alpha(0.34f));
            list.rounded_rect({r.x + 34.0f, r.y + r.h - 5.0f, r.w - 68.0f, 3.0f},
                              1.5f, theme::kLime.with_alpha(0.74f));
        }
        if (focused > 0.001f)
            plate_focus(c, kNavPlate, r, focused);
        text_shrink(c, tr(labels[i]), r.x + r.w * 0.5f,
                    baseline(r.y, r.h, theme::kSmall), theme::kSmall,
                    active || focused > 0.01f ? theme::kTitle : theme::kMuted,
                    r.w - 24.0f, Align::center);
    }
    text(c, clock_, 1848.0f, baseline(42.0f, 54.0f, theme::kClock), theme::kClock,
         theme::kTitle, Align::right);
    list.rounded_rect({72.0f, 126.0f, 1776.0f, 1.0f}, 0.0f, theme::kText.with_alpha(0.12f));
}

void Launcher::draw_frame(Canvas &c, const char *title, const char *copy)
{
    // Storage, Language and About are Settings subpages; keep the global TV shell visible so
    // entering a utility never feels like falling back to the old launcher.
    draw_top_nav(c, 3);
    text_shrink(c, title, 72.0f, baseline(142.0f, 38.0f, theme::kHeading), theme::kHeading,
                theme::kTitle, 1280.0f);
    text_shrink(c, copy, 72.0f, baseline(176.0f, 24.0f, 18.0f), 18.0f, theme::kMeta,
                1540.0f);
}

void Launcher::draw_footer(Canvas &c, const Hint *hints, int count)
{
    c.list.rounded_rect({108.0f, 955.0f, 1704.0f, 1.0f}, 0.0f, theme::kRule.with_alpha(0.9f));
    draw_hints(c, hints, count, 108.0f, 987.0f, theme::kCopy, 1704.0f);
}

void Launcher::draw_confirmation(Canvas &c)
{
    if (confirmation_ == Confirmation::none)
        return;

    const char *title = tr("Settings");
    if (confirmation_ == Confirmation::console_mode)
        title = tr("Console mode");
    else if (confirmation_ == Confirmation::mapping_reset)
        title = tr("Controls");
    else if (confirmation_ == Confirmation::shader_caches)
        title = tr("Diagnostics");

    c.list.rounded_rect(kScreen, 0.0f, theme::kScrim.with_alpha(0.74f));
    const Rect panel{548.0f, 354.0f, 824.0f, 330.0f};
    c.list.shadow({panel.x - 16.0f, panel.y - 12.0f, panel.w + 32.0f, panel.h + 36.0f},
                  38.0f, 74.0f, theme::kLime.with_alpha(0.20f));
    glass(c, panel, 30.0f, theme::kGlass.with_alpha(0.94f), theme::kLime.with_alpha(0.68f), 1.2f);
    c.list.rounded_rect({panel.x + 28.0f, panel.y + 34.0f, 6.0f, 94.0f}, 3.0f, theme::kLime);
    text_shrink(c, title, panel.x + 64.0f, baseline(panel.y + 38.0f, 54.0f, theme::kHeading),
                theme::kHeading, theme::kTitle, panel.w - 104.0f);
    text_block(c, message_, panel.x + 64.0f, baseline(panel.y + 142.0f, 38.0f, theme::kText24),
               theme::kText24, 40.0f, theme::kBody, panel.w - 128.0f, 2, kShrink);
    static constexpr Hint kConfirmHints[] = {
        {Pad::cross, TR("Confirm")}, {Pad::circle, TR("Cancel")}};
    draw_hints(c, kConfirmHints, 2, panel.x + 64.0f, panel.y + panel.h - 52.0f,
               theme::kText, panel.w - 128.0f);
}

void Launcher::draw_launch(Canvas &c)
{
    const float t = launch_.progress();
    // The menu dims, the game's cover steps forward, then everything goes dark.
    const float black = tween::cubic_in_out((t - 0.45f) / 0.55f);
    const float veil = std::max(0.90f * tween::cubic_out(t / 0.22f), black);
    c.list.rounded_rect(kScreen, 0.0f, theme::kScrim.with_alpha(veil));

    const float appear = tween::back_out(t / 0.38f);
    const float leave = 1.0f - tween::cubic_in_out((t - 0.60f) / 0.40f);
    c.list.push_opacity(tween::clamp01(t / 0.18f) * leave);
    c.list.push_transform(1.0f - 0.14f * (1.0f - appear) * motion(), 960.0f, 470.0f, 0.0f, 0.0f);
    const Rect art{810.0f, 300.0f, 300.0f, 300.0f};
    c.list.shadow({art.x - 10.0f, art.y - 4.0f, art.w + 20.0f, art.h + 20.0f}, 30.0f, 70.0f,
                  theme::kLime.with_alpha(0.22f));
    cover(c, launch_cover_, art, 20.0f, 1.0f);
    text(c, tr("STARTING"), 960.0f, 668.0f, theme::kSmall, theme::kLime, Align::center, 4.0f);
    text_fit(c, launch_title_, 960.0f, 716.0f, theme::kHeading, theme::kTitle, 1300.0f,
             Align::center);
    c.list.pop_transform();
    c.list.pop_opacity();
}

void Launcher::draw(gfx::DrawList &list)
{
    Canvas c{list, fonts_, textures_, backdrop_, time_};
    backdrop_.draw(list, textures_, dim_.value);

    const bool launching = !selected_game_.empty();
    const float zoom =
        launching ? 1.0f + 0.045f * tween::cubic_in_out(launch_.progress()) * motion() : 1.0f;
    list.push_transform(zoom, 960.0f, 540.0f, 0.0f, 0.0f);
    if (transition_.running)
    {
        // The old screen slides away as the new one arrives from the other side.
        const float t = transition_.progress();
        const float e = tween::cubic_in_out(t);
        const float direction = forward_ ? 1.0f : -1.0f;
        list.push_opacity(1.0f - tween::cubic_out(t / 0.55f));
        list.push_transform(1.0f, 0.0f, 0.0f, -direction * 56.0f * e * motion(), 0.0f);
        draw_screen(c, leaving_);
        list.pop_transform();
        list.pop_opacity();
        list.push_opacity(tween::cubic_out((t - 0.2f) / 0.8f));
        list.push_transform(1.0f, 0.0f, 0.0f, direction * 56.0f * (1.0f - e) * motion(), 0.0f);
        draw_screen(c, screen_);
        list.pop_transform();
        list.pop_opacity();
    }
    else
    {
        draw_screen(c, screen_);
    }
    if (modal_shown_ != Modal::none)
    {
        const float opened = tween::clamp01(modal_open_.value);
        list.rounded_rect(kScreen, 0.0f, theme::kScrim.with_alpha(0.69f * opened));
        if (modal_shown_ == Modal::game)
            draw_game(c, opened);
        else if (modal_shown_ == Modal::mods)
            draw_mods(c, opened);
        else if (modal_shown_ == Modal::mapping)
            draw_mapping(c, opened);
        else
            draw_dialog(c, modal_shown_, opened);
    }
    draw_confirmation(c);
    list.pop_transform();
    if (launching)
        draw_launch(c);

    // The launcher arrives out of the dark.
    const float arrival = 1.0f - tween::cubic_out(intro_ / (first_start_ ? 0.7f : 0.45f));
    if (arrival > 0.0f)
        list.rounded_rect(kScreen, 0.0f, Color{0.0f, 0.0f, 0.0f, arrival});
}

} // namespace pe::ui
