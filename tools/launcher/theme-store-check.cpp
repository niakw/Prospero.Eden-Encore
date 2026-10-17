// UI theme persistence round-trip: run on host only, never touches a console.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "settings_store.h"
#include <cassert>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>
#include <unistd.h>

int main() {
    char temp[] = "/tmp/encore-theme-XXXXXX";
    assert(mkdtemp(temp) != nullptr);
    const std::string file = std::string(temp) + "/theme.json";
    assert(Eden::LoadPreferences(file).ui_theme == 0);

    Eden::Preferences prefs = Eden::LoadPreferences(file);
    prefs.volume = 37;
    prefs.controller_layout = 0;
    prefs.ui_theme = 1;
    assert(Eden::SavePreferences(prefs, file));
    auto result = Eden::LoadPreferences(file);
    assert(result.ui_theme == 1);
    assert(result.volume == 37 && result.controller_layout == 0);

    std::ifstream stream(file);
    const std::string json((std::istreambuf_iterator<char>(stream)),
                           std::istreambuf_iterator<char>());
    assert(json.find("\"theme\": \"switch\"") != std::string::npos);

    result.ui_theme = 0;
    assert(Eden::SavePreferences(result, file));
    assert(Eden::LoadPreferences(file).ui_theme == 0);

    result.ui_theme = 2;
    assert(!Eden::SavePreferences(result, file));
    result.ui_theme = -1;
    assert(!Eden::SavePreferences(result, file));

    const std::string unexpected = std::string(temp) + "/invalid.json";
    std::ofstream(unexpected) << R"({"appearance":{"theme":"surprise"}})";
    assert(Eden::LoadPreferences(unexpected).ui_theme == 0);
    assert(Eden::LoadPreferences(file).volume == 37);

    (void)std::remove(file.c_str());
    (void)std::remove(unexpected.c_str());
    (void)rmdir(temp);
    return 0;
}
