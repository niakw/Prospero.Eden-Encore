// ProsperoEden - Launcher settings: the category list and its dialogs.
// Copyright (C) 2026 BlackBearReloaded
// SPDX-License-Identifier: GPL-3.0-or-later

#include "pe/ui/launcher.hpp"
#include "pe/ui/video_presets.hpp"

#include <algorithm>
#include <string>
#include <vector>

namespace pe::ui
{

using audio::Cue;

namespace
{

constexpr Rect kDialog{550.0f, 180.0f, 820.0f, 720.0f};
enum Category
{
    kVideo,
    kAudio,
    kControls,
    kAccessibility,
    kDiagnostics,
    kStorage,
    kLanguage,
    kCategoryCount,
};
constexpr const char *kCategories[kCategoryCount] = {
    TR("Video"), TR("Audio"), TR("Controls"), TR("Accessibility"), TR("Diagnostics"),
    TR("Storage"), TR("Language")};
// The same as headings: capitals differ by language, so each is its own text.
constexpr const char *kHeadings[kCategoryCount] = {
    TR("VIDEO"), TR("AUDIO"), TR("CONTROLS"), TR("ACCESSIBILITY"), TR("DIAGNOSTICS"),
    TR("STORAGE"), TR("LANGUAGE")};

// The Video dialog's rows, and the window that shows five of them (placed as a game's settings
// are).
enum VideoRow : int
{
    video_renderer,
    video_performance,
    video_output,
    video_resolution,
    video_filter,
    video_fsr_sharpness,
    video_anti_aliasing,
    video_refresh,
    video_overlay,
    kVideoRows,
};
constexpr float kVideoRowsTop = 334.0f;
constexpr float kVideoRowPitch = 96.0f;
constexpr float kVideoRowHeight = 94.0f;
constexpr int kVideoRowsShown = 5;
constexpr Rect kVideoWindow{592.0f, kVideoRowsTop, 736.0f,
                            kVideoRowPitch * (kVideoRowsShown - 1) + kVideoRowHeight};
// The sizes of Preferences::output, as every language writes them.
constexpr const char *kOutputs[] = {"1080p", "1440p", "2160p"};

const char *output_name(int output)
{
    return kOutputs[std::clamp(output, 0, 2)];
}

const char *on_off(bool value)
{
    return value ? tr("On") : tr("Off");
}

std::string percent(int value)
{
    return fill(tr("{0}%"), {std::to_string(value)});
}

std::string pick(const std::vector<std::string> &values, int index)
{
    return index >= 0 && index < static_cast<int>(values.size()) ?
               values[static_cast<std::size_t>(index)] : std::string{"-"};
}

std::string controller_profile_name(int layout, const ButtonMapping& mapping)
{
    const bool custom = mapping_is_custom(mapping, layout);
    if (layout == 1)
        return custom ? tr("Custom Switch") : tr("Switch");
    return custom ? tr("Custom PS5") : tr("PlayStation");
}

// A path that fits a label: the end is what tells folders apart.
std::string short_path(const std::string &path, std::size_t limit)
{
    return path.size() <= limit ? path : "..." + path.substr(path.size() - (limit - 3));
}

} // namespace

void Launcher::press_settings(Key key)
{
    if (key != Key::triangle)
        clear_confirmation();
    switch (key)
    {
    case Key::circle:
        open(Screen::home, false);
        return;
    case Key::left:
    case Key::right:
    {
        const int delta = key == Key::right ? 1 : -1;
        if (settings_.move(delta))
        {
            section_.value = 0.0f;
            section_.velocity = 0.0f;
            cue(Cue::focus);
        }
        return;
    }
    case Key::up:
    case Key::down:
        return;
    case Key::triangle:
    {
        if (!confirm_action(Confirmation::restore_defaults))
            return;
        const Preferences before = prefs_;
        const int language = prefs_.language;
        prefs_ = Preferences{};
        prefs_.language = language; // a recovery reset must not change the user's language
        if (!save_preferences(true))
        {
            prefs_ = before;
            apply_look();
            cue(Cue::error);
            return;
        }
        apply_look();
        say(tr("Recommended defaults restored."));
        cue(Cue::saved);
        return;
    }
    case Key::cross:
        press_ = 1.0f;
        switch (settings_.selected)
        {
        case kStorage:
            open(Screen::files, true);
            enter_files();
            break;
        case kLanguage:
            open(Screen::language, true);
            enter_language();
            break;
        case kVideo:
            open_modal(Modal::video);
            video_rows_.visible = kVideoRowsShown;
            video_rows_.pitch = kVideoRowPitch;
            video_rows_.reset(kVideoRows, 0);
            break;
        case kAudio:
            open_modal(Modal::audio);
            break;
        case kControls:
            open_modal(Modal::controls);
            break;
        case kAccessibility:
            open_modal(Modal::accessibility);
            break;
        default:
            open_modal(Modal::diagnostics);
            break;
        }
        return;
    default:
        return;
    }
}

void Launcher::draw_settings(Canvas &c)
{
    gfx::DrawList &list = c.list;
    draw_top_nav(c, 3);
    text_shrink(c, tr("Settings"), 72.0f, baseline(142.0f, 38.0f, theme::kHeading),
                theme::kHeading, theme::kTitle, 980.0f);
    text_shrink(c, tr("Fine-tune your experience"), 72.0f, baseline(176.0f, 24.0f, 18.0f),
                18.0f, theme::kMeta, 1200.0f);

    const std::string summaries[kCategoryCount] = {
        services_.performance_profile_labels()[static_cast<std::size_t>(
            std::clamp(prefs_.performance_profile, 0, kCustomVideoProfile))],
        prefs_.mute ? tr("Muted") : percent(prefs_.volume),
        controller_profile_name(prefs_.controller_layout, prefs_.mapping),
        prefs_.large_text || prefs_.high_contrast || prefs_.reduce_motion ? tr("On") : tr("Off"),
        prefs_.detailed_logging ? tr("Detailed logs on") : tr("Ready"),
        short_path(services_.files_folder(), 18),
        pick(services_.language_labels(), prefs_.language),
    };

    // ---- category rail: one row, controller-first ----
    constexpr float rail_x = 72.0f;
    constexpr float rail_y = 220.0f;
    constexpr float rail_w = 1776.0f;
    constexpr float gap = 14.0f;
    constexpr float card_h = 118.0f;
    constexpr float card_w = (rail_w - gap * float(kCategoryCount - 1)) / float(kCategoryCount);
    for (int row = 0; row < kCategoryCount; ++row)
    {
        const Rect r{rail_x + float(row) * (card_w + gap), rail_y, card_w, card_h};
        const bool selected = row == settings_.selected;
        if (selected)
            list.shadow({r.x - 4.0f, r.y - 3.0f, r.w + 8.0f, r.h + 10.0f},
                        24.0f, 32.0f, theme::kLime.with_alpha(0.16f));
        plate_rest(c, kTilePlate, r);
        if (selected)
            plate_focus(c, kTilePlate, r, 1.0f);
        text_shrink(c, tr(kCategories[row]), r.x + 18.0f,
                    baseline(r.y + 18.0f, 32.0f, 20.0f), 20.0f,
                    selected ? theme::kTitle : theme::kValue, r.w - 36.0f);
        text_shrink(c, summaries[row], r.x + 18.0f,
                    baseline(r.y + 65.0f, 24.0f, 15.0f), 15.0f,
                    selected ? theme::kLimePale : theme::kMeta, r.w - 36.0f);
        if (selected)
            list.rounded_rect({r.x + 18.0f, r.y + r.h - 10.0f, r.w - 36.0f, 3.0f},
                              1.5f, theme::kLime.with_alpha(0.80f));
    }

    // ---- selected category details ----
    struct Line { const char* label; std::string value; Pad first = Pad::none; Pad second = Pad::none; };
    std::vector<Line> lines;
    const char* about = "";
    switch (settings_.selected)
    {
    case kVideo:
        about = tr("Graphics backend and how games are scaled to your TV.");
        lines = {{tr("VIDEO PRESET"),
                  services_.performance_profile_labels()[static_cast<std::size_t>(
                      std::clamp(prefs_.performance_profile, 0, kCustomVideoProfile))]},
                 {tr("RENDERER"), prefs_.renderer != 0 ? tr("Vulkan (recommended)") : "OpenGL"},
                 {tr("TV OUTPUT"), output_name(prefs_.output)},
                 {tr("GAME RESOLUTION"), pick(services_.resolution_labels(), prefs_.resolution)},
                 {tr("UPSCALING FILTER"), pick(services_.filter_labels(), prefs_.filter)},
                 {tr("FSR SHARPNESS"), percent(prefs_.fsr_sharpness)},
                 {tr("ANTI-ALIASING"), pick(services_.anti_aliasing_labels(), prefs_.anti_aliasing)},
                 {tr("REFRESH RATE"), hertz(prefs_.refresh)},
                 {tr("FPS OVERLAY"), on_off(prefs_.hud)}};
        break;
    case kAudio:
        about = tr("Game volume, and the sounds of this menu.");
        lines = {{tr("GAME VOLUME"), percent(prefs_.volume)},
                 {tr("MUTE"), on_off(prefs_.mute)},
                 {tr("MENU SOUNDS"), prefs_.menu_volume > 0 ? percent(prefs_.menu_volume) : tr("Off")}};
        break;
    case kControls:
        about = tr("DualSense mapping, calibration, vibration and shortcuts.");
        lines = {{tr("BUTTON PROFILE"), controller_profile_name(prefs_.controller_layout, prefs_.mapping)},
                 {tr("BUTTON MAPPING"), mapping_is_custom(prefs_.mapping, prefs_.controller_layout) ? tr("Custom") : tr("Preset")},
                 {tr("VIBRATION"), on_off(prefs_.vibration)},
                 {tr("VIBRATION STRENGTH"), percent(prefs_.vibration_strength)},
                 {tr("STICK DEADZONE"), percent(prefs_.stick_deadzone)},
                 {tr("END GAME"), "", Pad::touchpad, Pad::l1},
                 {tr("FPS OVERLAY"), "", Pad::touchpad, Pad::r1}};
        break;
    case kAccessibility:
        about = tr("Make the menu easier to see and follow.");
        lines = {{tr("LARGER TEXT"), on_off(prefs_.large_text)},
                 {tr("HIGH CONTRAST"), on_off(prefs_.high_contrast)},
                 {tr("REDUCE MOTION"), on_off(prefs_.reduce_motion)}};
        break;
    case kDiagnostics:
    {
        const DiagnosticsInfo info = services_.diagnostics();
        about = tr("Runtime health, storage and recovery tools.");
        lines = {{tr("DETAILED LOGGING"), on_off(prefs_.detailed_logging)},
                 {tr("SETUP"), home_.setup_ready ? tr("Ready") : tr("Needs attention")},
                 {tr("FILESYSTEM"), info.filesystem},
                 {tr("FREE SPACE"), info.free_space},
                 {tr("SHADER/JIT CACHES"), info.shader_caches},
                 {tr("LOGS"), info.logs},
                 {tr("DATA"), short_path(info.data_path, 34)}};
        break;
    }
    case kStorage:
        about = tr("One root for keys, firmware, games, updates, mods and transfers.");
        lines = {{tr("ROOT"), short_path(services_.files_folder(), 34)},
                 {tr("LAYOUT"), tr("Fixed Encore folder structure")}};
        break;
    case kLanguage:
        about = tr("The language games use when they offer it.");
        lines = {{tr("LANGUAGE"), pick(services_.language_labels(), prefs_.language)},
                 {tr("REGION"), services_.language_region(prefs_.language)}};
        break;
    default:
        break;
    }

    const Rect detail{72.0f, 366.0f, 1776.0f, 530.0f};
    glass(c, detail, 28.0f, theme::kGlass.with_alpha(0.67f),
          theme::kPanelEdge.with_alpha(0.58f), 0.9f);
    const float shown = tween::clamp01(section_.value);
    list.push_opacity(shown);
    list.push_transform(1.0f, 0.0f, 0.0f, 0.0f, (1.0f - shown) * 10.0f * motion());
    text(c, tr(kHeadings[settings_.selected]), 108.0f,
         baseline(398.0f, 28.0f, theme::kSmall), theme::kSmall,
         theme::kLimePale, Align::left, 3.0f);
    text_shrink(c, about, 108.0f, baseline(438.0f, 38.0f, 22.0f), 22.0f,
                theme::kCopy, 1640.0f);
    list.rounded_rect({108.0f, 488.0f, 1704.0f, 1.0f}, 0.0f, theme::kRule.with_alpha(0.52f));

    constexpr int columns = 3;
    constexpr float tile_gap_x = 16.0f;
    constexpr float tile_gap_y = 14.0f;
    constexpr float tiles_x = 108.0f;
    constexpr float tiles_w = 1704.0f;
    constexpr float tile_w = (tiles_w - tile_gap_x * float(columns - 1)) / float(columns);
    constexpr float tile_h = 104.0f;
    constexpr float tiles_y = 516.0f;
    for (std::size_t i = 0; i < lines.size(); ++i)
    {
        const int column = int(i) % columns;
        const int row = int(i) / columns;
        const Rect tile{tiles_x + float(column) * (tile_w + tile_gap_x),
                        tiles_y + float(row) * (tile_h + tile_gap_y), tile_w, tile_h};
        list.bordered_rect(tile, 18.0f, theme::kPanel.with_alpha(0.48f), 1.0f,
                           theme::kPanelEdge.with_alpha(0.36f));
        text_shrink(c, lines[i].label, tile.x + 20.0f,
                    baseline(tile.y + 14.0f, 24.0f, 15.0f), 15.0f,
                    theme::kLabel, tile.w - 40.0f, Align::left, 1.5f);
        if (lines[i].first != Pad::none) {
            const float cy = tile.y + 69.0f;
            constexpr float icon_size = 30.0f;
            float px = tile.x + 20.0f;
            draw_pad(c, lines[i].first, px, cy, icon_size);
            px += pad_width(lines[i].first, icon_size) + 10.0f;
            text(c, "+", px, cy + 7.0f, 18.0f, theme::kMeta);
            px += 24.0f;
            draw_pad(c, lines[i].second, px, cy, icon_size);
        } else {
            text_shrink(c, lines[i].value, tile.x + 20.0f,
                        baseline(tile.y + 48.0f, 34.0f, 21.0f), 21.0f,
                        theme::kValue, tile.w - 40.0f);
        }
    }
    list.pop_transform();
    list.pop_opacity();

    if (!message_.empty())
        notice(c, message_, 108.0f, baseline(902.0f, 28.0f, 17.0f), 17.0f,
               message_warning_ ? theme::kWarning : theme::kLimePale, 1500.0f, message_warning_);

    static constexpr Hint kHints[] = {
        {Pad::leftright, TR("Browse settings")}, {Pad::cross, TR("Open")},
        {Pad::triangle, TR("Restore defaults")}, {Pad::circle, TR("Back")}};
    draw_footer(c, kHints, 4);
}

// ---------------------------------------------------------------- dialogs

int Launcher::dialog_rows(Modal modal) const
{
    switch (modal)
    {
    case Modal::video:
        return kVideoRows;
    case Modal::audio:
    case Modal::accessibility:
        return 3;
    case Modal::controls:
        return 5;
    case Modal::diagnostics:
        return 2;
    case Modal::game:
        // Complete per-game video overrides, button mapping and mods; save data in builds that
        // move saves.
        return services_.save_transfer_available() ? 12 : 11;
    default:
        return 1;
    }
}

float Launcher::dialog_row_top(Modal modal, int row) const
{
    switch (modal)
    {
    case Modal::controls:
        return 334.0f + 96.0f * static_cast<float>(row);
    case Modal::audio:
    case Modal::accessibility:
        return 370.0f + 102.0f * static_cast<float>(row);
    case Modal::diagnostics:
        return 570.0f + 102.0f * static_cast<float>(row);
    case Modal::video: // five of its rows show; the list scrolls to the others
        return kVideoRowsTop + kVideoRowPitch * static_cast<float>(row) - video_rows_.scroll();
    case Modal::game:
        return 334.0f + 96.0f * static_cast<float>(row);
    default:
        return 670.0f;
    }
}

void Launcher::press_dialog(Key key)
{
    const bool clearing_shader_cache =
        modal_ == Modal::diagnostics && option_ == 1 && key == Key::cross;
    if (!clearing_shader_cache)
        clear_confirmation();
    const int rows = dialog_rows(modal_);
    const bool adjust = key == Key::left || key == Key::right;
    const bool activate = key == Key::cross;
    const int step = key == Key::left ? -1 : 1;
    if (key == Key::circle)
    {
        close_modal();
        return;
    }
    if ((key == Key::up || key == Key::down) && modal_ == Modal::video)
    {
        if (video_rows_.move(key == Key::down ? 1 : -1))
        {
            option_ = video_rows_.selected;
            message_.clear();
            cue(Cue::focus);
        }
        return;
    }
    if ((key == Key::up || key == Key::down) && rows > 1)
    {
        option_ = (option_ + (key == Key::down ? 1 : rows - 1)) % rows;
        message_.clear();
        cue(Cue::focus);
        return;
    }
    if (!adjust && !activate)
        return;

    const Preferences before = prefs_;
    Cue sound = Cue::toggle;
    switch (modal_)
    {
    case Modal::video:
        if (option_ == video_renderer)
        {
            prefs_.renderer = prefs_.renderer != 0 ? 0 : 1;
            RefreshVideoProfile(prefs_);
        }
        else if (option_ == video_performance)
        {
            const int preset = CycleVideoPreset(prefs_.performance_profile, step);
            ApplyVideoPreset(prefs_, preset);
        }
        else if (option_ == video_output)
        {
            // The menu follows at once (the frontend opens its display again at this size).
            const int count = static_cast<int>(std::size(kOutputs));
            prefs_.output = (std::clamp(prefs_.output, 0, count - 1) + step + count) % count;
            RefreshVideoProfile(prefs_);
        }
        else if (option_ == video_resolution)
        {
            const int count = static_cast<int>(services_.resolution_labels().size());
            prefs_.resolution = (prefs_.resolution + step + count) % count;
            RefreshVideoProfile(prefs_);
        }
        else if (option_ == video_filter)
        {
            const int count = static_cast<int>(services_.filter_labels().size());
            prefs_.filter = (prefs_.filter + step + count) % count;
            RefreshVideoProfile(prefs_);
        }
        else if (option_ == video_fsr_sharpness)
        {
            if (!adjust) return;
            prefs_.fsr_sharpness = std::clamp(prefs_.fsr_sharpness + 5 * step, 0, 100);
            RefreshVideoProfile(prefs_);
            sound = Cue::slider;
        }
        else if (option_ == video_anti_aliasing)
        {
            const int count = static_cast<int>(services_.anti_aliasing_labels().size());
            prefs_.anti_aliasing = (prefs_.anti_aliasing + step + count) % count;
            RefreshVideoProfile(prefs_);
        }
        else if (option_ == video_refresh)
        {
            prefs_.refresh = prefs_.refresh != 0 ? 0 : 1;
            RefreshVideoProfile(prefs_);
        }
        else
            prefs_.hud = !prefs_.hud;
        break;
    case Modal::audio:
        if (option_ == 0)
        {
            if (!adjust)
                return;
            prefs_.volume = std::clamp(prefs_.volume + 10 * step, 0, 100);
            sound = Cue::slider;
        }
        else if (option_ == 1)
            prefs_.mute = !prefs_.mute;
        else
        {
            if (!adjust)
                return;
            prefs_.menu_volume = std::clamp(prefs_.menu_volume + 10 * step, 0, 100);
            sound = Cue::slider;
        }
        break;
    case Modal::controls:
        if (option_ == 0)
        {
            if (!adjust && !activate) return;
            prefs_.controller_layout = (prefs_.controller_layout + step + 2) % 2;
            prefs_.mapping = base_mapping_for_layout(prefs_.controller_layout);
            say(fill(tr("Controller profile: {0}"),
                     {controller_profile_name(prefs_.controller_layout, prefs_.mapping)}));
        }
        else if (option_ == 1)
        {
            if (activate) open_mapping(false);
            return;
        }
        else if (option_ == 2)
            prefs_.vibration = !prefs_.vibration;
        else if (option_ == 3)
        {
            if (!adjust) return;
            prefs_.vibration_strength = std::clamp(prefs_.vibration_strength + 10 * step, 0, 100);
            sound = Cue::slider;
        }
        else
        {
            if (!adjust) return;
            prefs_.stick_deadzone = std::clamp(prefs_.stick_deadzone + 2 * step, 0, 20);
            sound = Cue::slider;
        }
        break;
    case Modal::accessibility:
        if (option_ == 0)
            prefs_.large_text = !prefs_.large_text;
        else if (option_ == 1)
            prefs_.high_contrast = !prefs_.high_contrast;
        else
            prefs_.reduce_motion = !prefs_.reduce_motion;
        break;
    case Modal::diagnostics:
        if (option_ == 0)
        {
            prefs_.detailed_logging = !prefs_.detailed_logging;
        }
        else
        {
            if (!activate) return;
            if (!confirm_action(Confirmation::shader_caches)) return;
            std::string result;
            const bool cleared = services_.clear_shader_caches(&result);
            say(result, !cleared);
            cue(cleared ? Cue::saved : Cue::error);
            return;
        }
        break;
    default:
        return;
    }
    // The launcher's look changes on the spot: that is its own confirmation.
    if (!save_preferences(modal_ == Modal::accessibility))
    {
        prefs_ = before;
        sound = Cue::error;
    }
    else if (modal_ == Modal::video && option_ == video_refresh && prefs_.refresh == 1)
    {
        // 120 Hz is a request: the display has the last word.
        say(tr("Saved. A display that cannot show 120 Hz stays at 60 Hz."));
    }
    apply_look();
    cue(sound);
}

void Launcher::draw_dialog(Canvas &c, Modal modal, float open)
{
    gfx::DrawList &list = c.list;
    list.push_opacity(open);
    list.push_transform(1.0f - 0.03f * (1.0f - open) * motion(), 960.0f, 540.0f, 0.0f,
                        (1.0f - open) * 26.0f * motion());
    glass(c, kDialog, 26.0f, theme::kPanel.with_alpha(0.97f), theme::kPanelEdge.with_alpha(0.66f),
          1.6f);

    const char *title = "";
    const char *copy = "";
    switch (modal)
    {
    case Modal::video:
    {
        title = tr("Video");
        static constexpr const char *kAbout[kVideoRows] = {
            TR("Vulkan is recommended on PS5. Use OpenGL only as a fallback for a game with Vulkan issues."),
            TR("Minimum reduces GPU load and may use lower GPU accuracy for speed. Recommended balances quality and stability. High and Ultra raise image quality when the game has headroom."),
            TR("Final app output size. Choose 1080p for lower memory use, 1440p for balance, or 2160p for maximum output detail."),
            TR("Game render scale follows the selected profile. Lower it for performance or memory; raise it only when a game has headroom."),
            TR("Bilinear is the lightest default. AMD FSR is most useful when rendering below the TV output size."),
            TR("FSR sharpness changes detail recovery only when AMD FSR is selected. Lower it if the picture looks grainy or over-sharpened."),
            TR("Anti-aliasing smooths jagged edges. None is fastest; FXAA is light; SMAA prioritizes image quality."),
            TR("60 Hz is recommended. 120 Hz changes display mode only; the game still needs to render above 60 FPS to benefit."),
            TR("Shows live FPS while playing. Off is cleaner for normal use; Touchpad + R1 toggles it at any time.")};
        copy = tr(kAbout[std::clamp(option_, 0, kVideoRows - 1)]);
        break;
    }
    case Modal::audio:
        title = tr("Audio");
        copy = tr("Game audio; PS5 system-menu music is unchanged.");
        break;
    case Modal::controls:
    {
        title = tr("Controls");
        static constexpr const char *kAbout[] = {
            TR("PlayStation Auto keeps Cross/Circle menu semantics while adapting gameplay to physical Switch positions. Switch stays fixed; editing any button creates a custom profile."),
            TR("Customize every guest button. The profile automatically becomes Custom PS5 or Custom Switch."),
            TR("Turns DualSense vibration on or off for games."),
            TR("100% is full DualSense rumble strength. Lower it if vibration feels too strong."),
            TR("8% is recommended. Increase it for stick drift; decrease it for more sensitive aiming.")};
        copy = tr(kAbout[std::clamp(option_, 0, 4)]);
        break;
    }
    case Modal::accessibility:
        title = tr("Accessibility");
        copy = tr("Make the menu easier to see and follow.");
        break;
    default:
        title = tr("Diagnostics");
        copy = tr("Health and storage tools. Cache cleanup never removes saves, settings, keys or games.");
        break;
    }
    text_shrink(c, title, 592.0f, baseline(218.0f, 62.0f, theme::kDisplay), theme::kDisplay,
                theme::kTitle, 736.0f);
    text_shrink(c, copy, 592.0f, baseline(291.0f, 32.0f, theme::kSmall), theme::kSmall,
                Color::rgb(0xc5c1d2), 736.0f);

    const int rows = dialog_rows(modal);
    // Video's rows scroll in a window of five; the other dialogs show all of theirs.
    const bool scrolls = modal == Modal::video;
    const int first = scrolls ? video_rows_.first_row() : 0;
    const int last = scrolls ? video_rows_.last_row() : rows - 1;
    if (scrolls)
        list.push_clip({kVideoWindow.x - 24.0f, kVideoWindow.y - 6.0f, kVideoWindow.w + 48.0f,
                        kVideoWindow.h + 12.0f});
    for (int row = first; row <= last; ++row)
    {
        list.push_opacity(scrolls ? video_rows_.row_alpha(row, kVideoRowHeight) : 1.0f);
        plate_rest(c, kRowPlate, {592.0f, dialog_row_top(modal, row), 736.0f, 94.0f});
        list.pop_opacity();
    }
    plate_focus(c, kRowPlate,
                {592.0f,
                 scrolls ? kVideoRowsTop + video_rows_.cursor() - video_rows_.scroll() :
                           option_cursor_.value,
                 736.0f, 94.0f},
                1.0f);

    // A row's name takes what its control (`taken` wide, at the right) leaves of the row.
    const auto label = [&](int row, const char *value, float taken)
    {
        text_shrink(c, value, 628.0f, baseline(dialog_row_top(modal, row), 94.0f, theme::kText24),
                    theme::kText24, theme::kValue, 664.0f - taken - 28.0f);
    };
    const auto choice = [&](int row, const std::string &value)
    {
        return chooser(c, value, 1296.0f,
                       baseline(dialog_row_top(modal, row), 94.0f, theme::kText24),
                       row == option_ ? 1.0f : 0.0f, theme::kLimePale);
    };
    constexpr float kToggle = 64.0f;
    const auto row_centre = [&](int row) { return dialog_row_top(modal, row) + 47.0f; };
    const float knob = tween::clamp01(switches_[0].value);

    switch (modal)
    {
    case Modal::video:
    {
        const std::string values[] = {
            prefs_.renderer != 0 ? tr("Vulkan (recommended)") : "OpenGL",
            services_.performance_profile_labels()[static_cast<std::size_t>(std::clamp(prefs_.performance_profile, 0, kCustomVideoProfile))],
            output_name(prefs_.output),
            pick(services_.resolution_labels(), prefs_.resolution),
            pick(services_.filter_labels(), prefs_.filter),
            percent(prefs_.fsr_sharpness),
            pick(services_.anti_aliasing_labels(), prefs_.anti_aliasing),
            hertz(prefs_.refresh),
        };
        static constexpr const char *kNames[kVideoRows] = {
            TR("Renderer"), TR("Video preset"), TR("TV output"), TR("Game resolution"),
            TR("Upscaling filter"), TR("FSR sharpness"), TR("Anti-aliasing"),
            TR("Refresh rate"), TR("FPS overlay")};
        for (int row = first; row <= last; ++row)
        {
            list.push_opacity(video_rows_.row_alpha(row, kVideoRowHeight));
            if (row == video_overlay)
            {
                label(row, tr(kNames[row]), kToggle);
                toggle(c, 1292.0f, row_centre(row), knob);
            }
            else
            {
                label(row, tr(kNames[row]), choice(row, values[row]));
            }
            list.pop_opacity();
        }
        break;
    }
    case Modal::audio:
    {
        // A level row: its value at the right, the bar ending 20 before it (or where "100%"
        // would leave it), and the name in what remains.
        const auto level_row = [&](int row, const char *name, const std::string &value, int level)
        {
            const float shown =
                text(c, value, 1292.0f, baseline(dialog_row_top(modal, row), 94.0f, theme::kText24),
                     theme::kText24, theme::kLimePale, Align::right);
            const float gap = std::max(96.0f, shown + 20.0f);
            level_bar(c, 1292.0f - gap, row_centre(row), 260.0f, static_cast<float>(level) / 100.0f,
                      option_ == row ? 1.0f : 0.0f);
            label(row, name, 260.0f + gap);
        };
        level_row(0, tr("Game volume"), percent(prefs_.volume), prefs_.volume);
        label(1, tr("Mute"), kToggle);
        toggle(c, 1292.0f, row_centre(1), knob);
        level_row(2, tr("Menu sounds"), prefs_.menu_volume > 0 ? percent(prefs_.menu_volume) : tr("Off"),
                  prefs_.menu_volume);
        break;
    }
    case Modal::controls:
    {
        const auto level_row = [&](int row, const char *name, const std::string &value, int level, int maximum)
        {
            const float shown =
                text(c, value, 1292.0f, baseline(dialog_row_top(modal, row), 94.0f, theme::kText24),
                     theme::kText24, theme::kLimePale, Align::right);
            const float gap = std::max(96.0f, shown + 20.0f);
            level_bar(c, 1292.0f - gap, row_centre(row), 260.0f,
                      maximum > 0 ? static_cast<float>(level) / static_cast<float>(maximum) : 0.0f,
                      option_ == row ? 1.0f : 0.0f);
            label(row, name, 260.0f + gap);
        };
        const std::string profile = controller_profile_name(prefs_.controller_layout, prefs_.mapping);
        const std::string mapping = mapping_is_custom(prefs_.mapping, prefs_.controller_layout) ?
                                        tr("Edit custom mapping") : tr("Customize");
        label(0, tr("Button profile"), choice(0, profile));
        label(1, tr("Button mapping"), choice(1, mapping));
        label(2, tr("Vibration"), kToggle);
        toggle(c, 1292.0f, row_centre(2), tween::clamp01(switches_[1].value));
        level_row(3, tr("Vibration strength"), percent(prefs_.vibration_strength),
                  prefs_.vibration_strength, 100);
        level_row(4, tr("Stick deadzone"), percent(prefs_.stick_deadzone), prefs_.stick_deadzone, 20);
        break;
    }
    case Modal::accessibility:
    {
        static constexpr const char *kNames[] = {TR("Larger text"), TR("High contrast"),
                                                 TR("Reduce motion")};
        static constexpr const char *kAbout[] = {
            TR("Draws the menu's small text larger."),
            TR("Solid panels, brighter text and an outlined highlight."),
            TR("Stops the background drifting and the screens sliding, here and on the loading "
               "screen.")};
        for (int row = 0; row < 3; ++row)
        {
            label(row, tr(kNames[row]), kToggle);
            toggle(c, 1292.0f, row_centre(row),
                   tween::clamp01(switches_[static_cast<std::size_t>(row)].value));
        }
        // What the highlighted switch does.
        text_block(c, tr(kAbout[std::clamp(option_, 0, 2)]), 592.0f,
                   baseline(700.0f, 30.0f, theme::kSmall), theme::kSmall, 30.0f, theme::kMeta, 736.0f,
                   2, kShrink);
        break;
    }
    case Modal::diagnostics:
    {
        const DiagnosticsInfo info = services_.diagnostics();
        const std::string details =
            services_.setup_details() + "\n" +
            fill(tr("Filesystem: {0}  |  Free: {1}"), {info.filesystem, info.free_space}) + "\n" +
            fill(tr("Shader/JIT caches: {0}  |  Logs: {1}"), {info.shader_caches, info.logs}) + "\n" +
            fill(tr("Data: {0}"), {info.data_path});
        text_block(c, details, 592.0f, baseline(350.0f, 30.0f, theme::kSmall),
                   theme::kSmall, 30.0f, theme::kBody, 736.0f, 6, kShrink);
        label(0, tr("Detailed logging"), kToggle);
        toggle(c, 1292.0f, row_centre(0), knob);
        label(1, tr("Clear shader caches"), choice(1, tr("Clear")));
        break;
    }
    default:
        text_block(c, services_.setup_details(), 592.0f, baseline(364.0f, 40.0f, theme::kText24),
                   theme::kText24, 40.0f, theme::kBody, 736.0f, 7);
        label(0, tr("Detailed logging"), kToggle);
        toggle(c, 1292.0f, row_centre(0), knob);
        break;
    }

    if (scrolls)
    {
        list.pop_clip();
        scrollbar(c, video_rows_, 1340.0f, kVideoWindow.y, kVideoWindow.h);
    }

    // Under the rows: Video's five end lower than the other dialogs' three.
    const float foot = modal == Modal::video || modal == Modal::controls ? 848.0f : 811.0f;
    if (!message_.empty())
    {
        notice(c, message_, 592.0f, foot + 7.0f, theme::kSmall,
               message_warning_ ? theme::kWarning : theme::kLimePale, 736.0f, message_warning_);
    }
    else if (modal == Modal::controls && option_ == 1)
    {
        static constexpr Hint kOpen[] = {
            {Pad::updown, TR("Select")}, {Pad::cross, TR("Open")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kOpen, 3, 592.0f, foot, theme::kCopy, 736.0f);
    }
    else if (rows > 1)
    {
        static constexpr Hint kHints[] = {
            {Pad::updown, TR("Select")}, {Pad::leftright, TR("Change")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kHints, 3, 592.0f, foot, theme::kCopy, 736.0f);
    }
    else
    {
        static constexpr Hint kHints[] = {{Pad::cross, TR("Change")}, {Pad::circle, TR("Back")}};
        draw_hints(c, kHints, 2, 592.0f, foot, theme::kCopy, 736.0f);
    }
    list.pop_transform();
    list.pop_opacity();
}

} // namespace pe::ui
