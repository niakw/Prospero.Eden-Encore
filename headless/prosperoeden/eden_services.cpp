// SPDX-License-Identifier: GPL-3.0-or-later
#include "eden_services.h"

#include "assets_dir.h"
#include "crash_report.h"
#include "diagnostics.h"
#include "metadata_bridge.h"
#include "mods.h"
#include "native_directory.h"
#include "pe/core/strings.hpp"
#include "common/net/net.h"
#include "radio_input.h"
#include "version.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <dirent.h>
#include <exception>
#include <fcntl.h>
#include <filesystem>
#include <future>
#include <initializer_list>
#include <nlohmann/json.hpp>
#include <stb_image.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

using pe::fill;
using pe::tr;

bool IsFile(const std::string& path) {
    struct stat info {};
    if (lstat(path.c_str(), &info) == 0) return S_ISREG(info.st_mode);
    if (errno != EPERM && errno != EACCES) return false;
    return stat(path.c_str(), &info) == 0 && S_ISREG(info.st_mode);
}

std::uint64_t TitleIdFromFilename(const std::string& file) {
    for (std::size_t open = file.find('['); open != std::string::npos;
         open = file.find('[', open + 1)) {
        const std::size_t close = file.find(']', open + 1);
        if (close == std::string::npos || close - open != 17) continue;
        std::uint64_t value = 0;
        bool valid = true;
        for (std::size_t i = open + 1; i < close; ++i) {
            const unsigned char c = static_cast<unsigned char>(file[i]);
            unsigned digit = 0;
            if (c >= '0' && c <= '9') digit = c - '0';
            else if (c >= 'a' && c <= 'f') digit = c - 'a' + 10;
            else if (c >= 'A' && c <= 'F') digit = c - 'A' + 10;
            else { valid = false; break; }
            value = (value << 4) | digit;
        }
        if (valid && value != 0) return value;
    }
    return 0;
}

std::uint64_t ResolveTitleId(const std::string& path, const std::string& file) {
    const std::uint64_t metadata_id = eden_game_title_id(path.c_str());
    if (metadata_id != 0) return metadata_id;
    const std::uint64_t filename_id = TitleIdFromFilename(file);
    if (filename_id != 0)
        std::fprintf(stderr, "EDEN_TITLE_ID_FALLBACK file=%s title_id=%016llX\n", file.c_str(),
                     static_cast<unsigned long long>(filename_id));
    return filename_id;
}

std::string NlibHeroPath(std::uint64_t title_id) {
    char id[17]{};
    std::snprintf(id, sizeof(id), "%016llX", static_cast<unsigned long long>(title_id));
    return Eden::CoversDir() + "/hero-" + id + ".tga";
}

bool WriteJpegTga(const std::string& encoded, const std::string& output) {
    int width = 0;
    int height = 0;
    int channels = 0;
    unsigned char* rgba = stbi_load_from_memory(
        reinterpret_cast<const unsigned char*>(encoded.data()), static_cast<int>(encoded.size()),
        &width, &height, &channels, 4);
    if (!rgba || width <= 0 || height <= 0 || width > 4096 || height > 4096) {
        stbi_image_free(rgba);
        return false;
    }

    std::FILE* file = std::fopen(output.c_str(), "wb");
    if (!file) {
        stbi_image_free(rgba);
        return false;
    }

    unsigned char header[18]{};
    header[2] = 2;
    header[12] = static_cast<unsigned char>(width);
    header[13] = static_cast<unsigned char>(width >> 8);
    header[14] = static_cast<unsigned char>(height);
    header[15] = static_cast<unsigned char>(height >> 8);
    header[16] = 32;
    header[17] = 0x28; // top-left origin + 8 alpha bits
    bool ok = std::fwrite(header, 1, sizeof(header), file) == sizeof(header);
    std::vector<unsigned char> row(static_cast<std::size_t>(width) * 4);
    for (int y = 0; ok && y < height; ++y) {
        const unsigned char* source = rgba + static_cast<std::size_t>(y) * row.size();
        for (int x = 0; x < width; ++x) {
            row[4 * x + 0] = source[4 * x + 2];
            row[4 * x + 1] = source[4 * x + 1];
            row[4 * x + 2] = source[4 * x + 0];
            row[4 * x + 3] = source[4 * x + 3];
        }
        ok = std::fwrite(row.data(), 1, row.size(), file) == row.size();
    }
    ok = std::fclose(file) == 0 && ok;
    stbi_image_free(rgba);
    return ok;
}

std::string NlibPlayersPath(std::uint64_t title_id) {
    char id[17]{};
    std::snprintf(id, sizeof(id), "%016llX", static_cast<unsigned long long>(title_id));
    return Eden::CoversDir() + "/players-" + id + ".txt";
}

std::string CachedNlibHero(std::uint64_t title_id) {
    if (title_id == 0) return {};
    const std::string path = NlibHeroPath(title_id);
    return IsFile(path) ? path : std::string{};
}

int CachedNlibPlayers(std::uint64_t title_id) {
    if (title_id == 0) return 0;
    std::FILE* file = std::fopen(NlibPlayersPath(title_id).c_str(), "rb");
    if (!file) return 0;
    int players = 0;
    const int read = std::fscanf(file, "%d", &players);
    (void)std::fclose(file);
    return read == 1 && players > 0 && players <= 16 ? players : 0;
}

void CacheNlibPlayers(std::uint64_t title_id, int players) {
    if (title_id == 0 || players <= 0 || players > 16) return;
    (void)mkdir(Eden::CoversDir().c_str(), 0777);
    const std::string path = NlibPlayersPath(title_id);
    const std::string staged = path + ".new";
    std::FILE* file = std::fopen(staged.c_str(), "wb");
    if (!file) return;
    const bool written = std::fprintf(file, "%d\n", players) > 0;
    const bool closed = std::fclose(file) == 0;
    if (!written || !closed || std::rename(staged.c_str(), path.c_str()) != 0)
        (void)std::remove(staged.c_str());
}

struct NlibEnrichment {
    std::string hero;
    int max_players = 0;
};

// Nlib is optional enrichment only: the ROM's embedded icon remains the offline fallback.
// Called from the asynchronous library scan, never from the launcher render/input thread.
NlibEnrichment EnsureNlibEnrichment(std::uint64_t title_id) {
    NlibEnrichment result;
    if (title_id == 0) return result;

    result.hero = CachedNlibHero(title_id);
    result.max_players = CachedNlibPlayers(title_id);

    char id[17]{};
    std::snprintf(id, sizeof(id), "%016llX", static_cast<unsigned long long>(title_id));
    std::fprintf(stderr, "EDEN_NLIB_BEGIN title_id=%s cached_hero=%d cached_players=%d\n", id,
                 !result.hero.empty(), result.max_players);

    try {
        if (result.max_players == 0) {
            const std::string endpoint = std::string{"/nx/"} + id + "?fields=numberOfPlayers";
            if (const auto response = Common::Net::MakeRequest("https://api.nlib.cc", endpoint)) {
                const auto json = nlohmann::json::parse(*response);
                const int players = json.value("numberOfPlayers", 0);
                if (players > 0 && players <= 16) {
                    result.max_players = players;
                    CacheNlibPlayers(title_id, players);
                }
            }
        }

        if (result.hero.empty()) {
            const std::string endpoint = std::string{"/nx/"} + id + "/banner/720p";
            if (const auto response = Common::Net::MakeRequest("https://api.nlib.cc", endpoint)) {
                const std::string& body = *response;
                if (body.size() >= 4096 && body.size() <= (10u << 20) &&
                    static_cast<unsigned char>(body[0]) == 0xff &&
                    static_cast<unsigned char>(body[1]) == 0xd8) {
                    (void)mkdir(Eden::CoversDir().c_str(), 0777);
                    const std::string path = NlibHeroPath(title_id);
                    const std::string staged = path + ".new";
                    if (WriteJpegTga(body, staged) && std::rename(staged.c_str(), path.c_str()) == 0) {
                        result.hero = path;
                        Eden::Report("artwork", (std::string{"Nlib hero cached for "} + id).c_str());
                    } else {
                        (void)std::remove(staged.c_str());
                    }
                }
            }
        }
    } catch (const std::exception& error) {
        Eden::Report("artwork", (std::string{"Nlib unavailable: "} + error.what()).c_str());
    }

    std::fprintf(stderr, "EDEN_NLIB_RESULT title_id=%s hero=%d players=%d\n", id,
                 !result.hero.empty(), result.max_players);
    return result;
}

std::uintmax_t TreeBytes(const std::filesystem::path& root) {
    std::error_code error;
    if (!std::filesystem::exists(root, error)) return 0;
    std::uintmax_t bytes = 0;
    std::filesystem::recursive_directory_iterator it(
        root, std::filesystem::directory_options::skip_permission_denied, error), end;
    while (!error && it != end) {
        std::error_code entry_error;
        if (it->is_regular_file(entry_error)) {
            const auto size = it->file_size(entry_error);
            if (!entry_error) bytes += size;
        }
        it.increment(error);
        if (error) error.clear(); // Skip an unreadable entry and continue where possible.
    }
    return bytes;
}

std::string StorageSize(std::uintmax_t bytes) {
    constexpr std::uintmax_t KiB = 1024;
    constexpr std::uintmax_t MiB = KiB * 1024;
    constexpr std::uintmax_t GiB = MiB * 1024;
    char text[64];
    if (bytes >= GiB)
        std::snprintf(text, sizeof(text), "%.1f GB", static_cast<double>(bytes) / static_cast<double>(GiB));
    else if (bytes >= MiB)
        std::snprintf(text, sizeof(text), "%.1f MB", static_cast<double>(bytes) / static_cast<double>(MiB));
    else
        std::snprintf(text, sizeof(text), "%.0f KB", static_cast<double>(bytes) / static_cast<double>(KiB));
    return text;
}

// A game's update and DLC: "Update 1.2.0, 2 DLC"; brief leaves the word out ("v1.2.0, 2 DLC") for
// places with little room.
std::string AddOnSummary(uint64_t title_id, bool brief = false) {
    char update[64]{};
    unsigned dlc = 0;
    eden_game_addons(title_id, update, sizeof(update), &dlc);
    std::string text;
    if (update[0]) text = brief ? (update[0] == 'v' ? std::string{update} : "v" + std::string{update}) :
                                  fill(tr("Update {0}"), {update});
    if (dlc) text += (text.empty() ? "" : ", ") + fill(tr("{0} DLC"), {std::to_string(dlc)});
    return text;
}

// The language a game will use for the chosen one (Settings > Language), and a note when the game
// does not offer the choice and falls back to another language.
struct GameLanguage {
    std::string label;
    std::string note;
};
GameLanguage LanguageFor(const std::string& path, uint64_t title_id, int choice) {
    const int chosen = Eden::kLanguageSettings[choice];
    const int used = eden_game_language(path.c_str(), Eden::AssetsPath("keys").c_str(), title_id, chosen);
    GameLanguage result{tr(Eden::kLanguageLabels[choice]), {}};
    if (used == chosen) return result;
    result.label = tr("Another language");
    for (std::size_t i = 0; i < std::size(Eden::kLanguageSettings); ++i)
        if (Eden::kLanguageSettings[i] == used) result.label = tr(Eden::kLanguageLabels[i]);
    result.note = fill(tr("{0} not available"), {tr(Eden::kLanguageLabels[choice])});
    return result;
}

// Why a game did not start, as headless/main.cpp reports it. The reasons that are whole sentences
// are shown in the player's language; the others carry codes and file names and stay as they are.
// (tools/launcher/strings.py checks that main.cpp still says these.)
constexpr const char* kLaunchErrors[] = {
    TR("Selected ROM is no longer available"),
    TR("PS5 controller initialization failed"),
    TR("Graphics backend initialization failed. Try another backend in Settings; see stderr.log and eden_log.txt for "
       "driver details."),
    TR("The game ran out of graphics memory. Lower the resolution in Settings, Video (or in the game's own settings) "
       "and start it again."),
};
std::string LaunchError(const std::string& reason) {
    std::string text = reason;
    for (const char* known : kLaunchErrors)
        if (reason == known) text = tr(known);
    // "Details:" follows it: a reason without its own full stop gets one.
    if (!text.empty() && text.back() != '.' && text.back() != '!' && text.back() != '?') text += '.';
    return text;
}

// Names of the subfolders (folders = true) or regular files in path, sorted without regard
// to case. Unlike ReadNativeDirectory, an odd entry is skipped rather than failing the
// folder: the Storage browser walks available roots/directories so an external root can be chosen.
std::vector<std::string> ListEntries(const std::string& path, bool folders, bool& ok) {
    ok = false;
    std::vector<std::string> names;
    const int fd = open(path.c_str(), O_RDONLY | O_DIRECTORY);
    if (fd < 0) return names;
    std::vector<char> buffer(65536);
    for (;;) {
        const int count = sceKernelGetdents(fd, buffer.data(), static_cast<int>(buffer.size()));
        if (count == 0) { ok = true; break; }
        if (count < 0 || count > static_cast<int>(buffer.size())) break;
        for (std::size_t offset = 0; offset + offsetof(dirent, d_name) < static_cast<std::size_t>(count);) {
            uint16_t length;
            uint8_t type;
            std::memcpy(&length, buffer.data() + offset + offsetof(dirent, d_reclen), sizeof(length));
            std::memcpy(&type, buffer.data() + offset + offsetof(dirent, d_type), sizeof(type));
            if (length <= offsetof(dirent, d_name) || offset + length > static_cast<std::size_t>(count)) break;
            const char* name = buffer.data() + offset + offsetof(dirent, d_name);
            const std::string entry(name, strnlen(name, length - offsetof(dirent, d_name)));
            offset += length;
            if (entry.empty() || entry == "." || entry == "..") continue;
            if (type == DT_LNK) continue;
            bool is_folder = type == DT_DIR, is_file = type == DT_REG;
            if (type == DT_UNKNOWN) {
                struct stat info {};
                const std::string full = path == "/" ? "/" + entry : path + "/" + entry;
                if (lstat(full.c_str(), &info) == 0) {
                    if (S_ISLNK(info.st_mode)) continue;
                } else if (errno != EPERM && errno != EACCES) {
                    continue;
                } else if (stat(full.c_str(), &info) != 0) {
                    continue;
                }
                is_folder = S_ISDIR(info.st_mode);
                is_file = S_ISREG(info.st_mode);
            }
            if (folders ? is_folder : is_file) names.push_back(entry);
        }
    }
    close(fd);
    const auto lower = [](std::string text) {
        for (char& c : text) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        return text;
    };
    std::sort(names.begin(), names.end(), [&](const std::string& a, const std::string& b) {
        return lower(a) < lower(b);
    });
    return names;
}

std::string JoinPath(const std::string& directory, const std::string& name) {
    return directory == "/" ? "/" + name : directory + "/" + name;
}

// Files in directory with one of the (lower-case) extensions; -1 when it cannot be read.
int CountFiles(const std::string& directory, std::initializer_list<const char*> extensions) {
    bool ok = false;
    int count = 0;
    for (const auto& name : ListEntries(directory, false, ok)) {
        std::string lower = name;
        for (char& c : lower) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        for (const char* extension : extensions)
            if (lower.size() > std::strlen(extension) && lower.ends_with(extension)) { ++count; break; }
    }
    return ok ? count : -1;
}

unsigned int HashPath(const std::string& path) {
    unsigned int hash = 2166136261u;
    for (const unsigned char byte : path) hash = (hash ^ byte) * 16777619u;
    return hash;
}

// A title from the file's name: without its extension and the tags dumps carry
// ("Name [0100...][v0]", "Name (USA)").
std::string CleanTitle(const std::string& filename) {
    std::string title = std::filesystem::path(filename).stem().string();
    if (title.rfind("[Game] ", 0) == 0) title.erase(0, 7);
    if (const auto tag = title.find_first_of("[("); tag != std::string::npos && tag > 0) title.erase(tag);
    while (!title.empty() && (title.back() == ' ' || title.back() == '_' || title.back() == '-')) title.pop_back();
    return title.empty() ? std::filesystem::path(filename).stem().string() : title;
}

// Covers are keyed by the ROM's file name, not its full path, so they survive a new game
// files folder.
std::string CoverPath(const std::string& filename) {
    char name[16]{};
    std::snprintf(name, sizeof(name), "/%08x.tga", HashPath(filename));
    return Eden::CoversDir() + name;
}

// The game's own name is kept beside its cover once the ROM has been read, so the home screen
// can name its games without opening them.
std::string NamePath(const std::string& filename) {
    char name[16]{};
    std::snprintf(name, sizeof(name), "/%08x.name", HashPath(filename));
    return Eden::CoversDir() + name;
}

std::string SavedTitle(const std::string& filename) {
    char text[513]{};
    if (std::FILE* file = std::fopen(NamePath(filename).c_str(), "rb")) {
        const std::size_t size = std::fread(text, 1, sizeof(text) - 1, file);
        std::fclose(file);
        text[size] = '\0';
    }
    return text;
}

void SaveTitle(const std::string& filename, const std::string& title) {
    if (title.empty() || SavedTitle(filename) == title) return;
    const std::string path = NamePath(filename);
    const std::string staged = path + ".new";
    std::FILE* file = std::fopen(staged.c_str(), "wb");
    if (!file) return;
    const bool written = std::fwrite(title.data(), 1, title.size(), file) == title.size();
    if (std::fclose(file) != 0 || !written || std::rename(staged.c_str(), path.c_str()) != 0)
        (void)std::remove(staged.c_str());
}

std::string GameTitle(const std::string& filename) {
    const std::string saved = SavedTitle(filename);
    return saved.empty() ? CleanTitle(filename) : saved;
}

// The cached cover of a ROM, extracted from it when missing; empty when it has none.
std::string EnsureCover(const std::string& filename, std::string* title = nullptr) {
    const std::string cover = CoverPath(filename);
    if (Eden::FileExists(cover) && !title) return cover;
    const std::string rom = Eden::AssetsPath("roms/" + filename);
    if (!Eden::FileExists(rom)) return {};
    (void)mkdir(Eden::CoversDir().c_str(), 0777);
    char extracted[513]{};
    const int metadata = eden_extract_game_metadata(rom.c_str(), Eden::AssetsPath("keys").c_str(), cover.c_str(),
                                                    extracted, sizeof(extracted));
    if (metadata & EDEN_METADATA_TITLE) {
        SaveTitle(filename, extracted);
        if (title) *title = extracted;
    }
    if (metadata & EDEN_METADATA_COVER) return cover;
    Eden::Report("cover", ("No cover extracted from " + filename).c_str());
    return Eden::FileExists(cover) ? cover : std::string{};
}

int CountInstalledGames() {
    std::error_code error;
    const auto entries = Eden::ReadNativeDirectory(Eden::AssetsPath("roms"), error);
    if (error) return 0;
    int count = 0;
    for (const auto& entry : entries) {
        const std::string filename = entry.path().filename().string();
        if (Eden::ValidRomFilename(filename) && IsFile(Eden::AssetsPath("roms/" + filename))) ++count;
    }
    return count;
}

// The labels of a setting, in the player's language (tools/launcher/strings.py lists them).
template <std::size_t N>
std::vector<std::string> Labels(const char* const (&values)[N]) {
    std::vector<std::string> labels;
    for (const char* value : values) labels.emplace_back(tr(value));
    return labels;
}

// What is missing from the setup, as metadata_bridge.cpp words it, in the player's language. Each
// message is one of these texts, with a folder or a code where it says {0}.
std::string SetupMessage(const std::string& english) {
    static constexpr const char* kMessages[] = {
        TR("Missing or empty keys/prod.keys in {0}."),
        TR("prod.keys could not supply an NCA header key. Replace it with a valid key dump."),
        TR("Cannot read firmware/ in {0}. Install extracted firmware NCAs."),
        TR("A firmware NCA cannot be read. Reinstall the firmware dump."),
        TR("Firmware NCA validation failed (code {0}). Check that firmware and prod.keys are compatible."),
        TR("No firmware NCAs found in {0}."),
        TR("Firmware SystemVersion data is missing or unreadable. Install a complete firmware dump."),
        TR("Setup validation failed. Check that firmware and key files are readable and valid."),
    };
    for (const std::string_view pattern : kMessages) {
        const std::size_t hole = pattern.find("{0}");
        if (hole == std::string_view::npos) {
            if (english == pattern) return tr(english);
            continue;
        }
        const std::string_view before = pattern.substr(0, hole);
        const std::string_view after = pattern.substr(hole + 3);
        if (english.size() >= before.size() + after.size() && english.starts_with(before) &&
            english.ends_with(after))
            return fill(tr(std::string(pattern)),
                        {std::string_view{english}.substr(before.size(),
                                                           english.size() - before.size() - after.size())});
    }
    return english;
}

} // namespace

EdenServices::EdenServices(std::string launch_error)
    : launch_error_(std::move(launch_error)),
      resolution_labels_(Labels(Eden::kResolutionLabels)),
      resolution_keys_(Labels(Eden::kResolutionKeys)),
      filter_labels_(Labels(Eden::kUpscalingFilterLabels)),
      anti_aliasing_labels_(Labels(Eden::kAntiAliasingLabels)),
      performance_profile_labels_(Labels(Eden::kPerformanceProfileLabels)),
      language_labels_(Labels(Eden::kLanguageLabels)) {
    (void)mkdir(Eden::ConfigDir().c_str(), 0777);
    setup_ = eden_startup_error();
    Eden::Report("setup", setup_.empty() ? "Keys and firmware startup checks passed" : setup_.c_str());
}

pe::ui::Home EdenServices::home() {
    const std::lock_guard lock(bridge_);
    pe::ui::Home home;
    home.setup_ready = setup_.empty();
    if (!home.setup_ready) {
        home.status = fill(tr("Setup required: {0} Open Settings, Storage to choose the root that holds the standard "
                              "keys, firmware and roms folders (or add the files to {1}), then reopen Encore."),
                           {SetupMessage(setup_), Eden::AssetsDir()});
    } else if (launch_error_.starts_with(Eden::Crash::kNotice)) {
        // The previous run ended with a crash report (headless/crash_report.h).
        home.status = fill(tr("ProsperoEden stopped because of an error. A report was saved to {0}."),
                           {launch_error_.substr(Eden::Crash::kNotice.size())});
        home.launch_failed = true;
    } else if (!launch_error_.empty()) {
        home.status = fill(tr("Game could not start: {0} Details: {1}"),
                           {LaunchError(launch_error_), Eden::LogFile("stderr.log")});
        home.launch_failed = true;
    }

    home.last_file = Eden::LoadLastGame();
    // If the last game was removed, fall back to the most recent one that still exists.
    if (!home.last_file.empty() && !IsFile(Eden::AssetsPath("roms/" + home.last_file))) {
        home.last_file.clear();
        for (const auto& name : Eden::LoadRecentGames()) {
            if (Eden::ValidRomFilename(name) && IsFile(Eden::AssetsPath("roms/" + name))) {
                home.last_file = name;
                break;
            }
        }
    }
    const std::string last_path = Eden::AssetsPath("roms/" + home.last_file);
    home.last_exists = !home.last_file.empty() && IsFile(last_path);
    if (!home.last_file.empty()) {
        std::string title = GameTitle(home.last_file);
        std::string cover = CoverPath(home.last_file);
        bool has_cover = Eden::FileExists(cover);
        if (home.last_exists && home.setup_ready && !has_cover) {
            cover = EnsureCover(home.last_file, &title);
            has_cover = !cover.empty();
        }
        home.last_title = title;
        home.last_caption = home.last_exists ? tr("Last game opened") :
                                               tr("ROM missing from the storage root");
        home.last_caption_warning = !home.last_exists;
        if (has_cover) home.last_cover = cover;
    }
    // The last game's update and DLC and the language it will use; when it does not offer the
    // chosen one, the caption says so. The same metadata is reused by Recent cards so selecting
    // one can become the Home hero without opening the full library first.
    const int selected_language = Eden::LoadPreferences().language;
    if (home.setup_ready)
        eden_scan_addons(Eden::AssetsPath("updates").c_str(), Eden::AssetsPath("keys").c_str());
    if (home.setup_ready && home.last_exists) {
        const uint64_t title_id = ResolveTitleId(last_path, home.last_file);
        const GameLanguage language = LanguageFor(last_path, title_id, selected_language);
        home.last_title_id = title_id;
        home.last_hero = CachedNlibHero(title_id);
        home.last_max_players = CachedNlibPlayers(title_id);
        home.last_addons = AddOnSummary(title_id);
        home.last_language = language.label;
        if (!language.note.empty()) {
            home.last_caption = language.note;
            home.last_caption_warning = true;
        }
    }

    auto history = Eden::LoadRecentGames();
    if (history.empty() && home.last_exists) {
        if (!Eden::SaveRecentGame(home.last_file))
            Eden::Report("history", "Could not seed recent games from last played game");
        history.push_back(home.last_file);
    }
    for (const auto& name : history) {
        const std::string recent_path = Eden::AssetsPath("roms/" + name);
        if (!IsFile(recent_path)) continue;
        pe::ui::Recent recent;
        recent.file = name;
        recent.title = GameTitle(name);
        recent.cover = EnsureCover(name);
        if (home.setup_ready) {
            recent.title_id = ResolveTitleId(recent_path, name);
            if (recent.title_id != 0) {
                recent.hero = CachedNlibHero(recent.title_id);
                recent.max_players = CachedNlibPlayers(recent.title_id);
                recent.addons = AddOnSummary(recent.title_id);
                recent.language = LanguageFor(recent_path, recent.title_id, selected_language).label;
            }
        }
        home.recents.push_back(std::move(recent));
        if (home.recents.size() == 4) break;
    }
    const int installed = CountInstalledGames();
    home.system_status = fill(installed == 1 ? tr("{0} game installed") : tr("{0} games installed"),
                              {std::to_string(installed)}) +
        "  /  " + (home.setup_ready ? tr("Firmware ready") : tr("Setup required"));
    return home;
}

std::string EdenServices::clock() {
    const std::time_t now = std::time(nullptr);
    char label[32]{};
    if (const std::tm* local = std::localtime(&now))
        (void)std::strftime(label, sizeof(label), "%H:%M", local);
    return label;
}

unsigned EdenServices::controllers() { return radio_input_controllers(); }

std::string EdenServices::version() {
    return Eden::kAppVersion;
}

std::vector<pe::ui::Game> EdenServices::games() {
    // The launcher reads the list beside its menu (pe/ui/library.cpp), so the metadata reader
    // is used by one thread at a time.
    std::unique_lock lock(bridge_);
    std::vector<pe::ui::Game> games;
    (void)mkdir(Eden::ConfigDir().c_str(), 0777);
    (void)mkdir(Eden::CoversDir().c_str(), 0777);
    std::error_code directory_error;
    const auto entries = Eden::ReadNativeDirectory(Eden::AssetsPath("roms"), directory_error);
    if (directory_error) return games;
    eden_scan_addons(Eden::AssetsPath("updates").c_str(), Eden::AssetsPath("keys").c_str());
    const int language_choice = Eden::LoadPreferences().language;
    // Network artwork is deliberately limited to what Home can display. The library scan stays
    // bounded even with a very large ROM collection: last played + at most four recent games.
    std::vector<std::string> artwork_files = Eden::LoadRecentGames();
    if (artwork_files.size() > 4) artwork_files.resize(4);
    const std::string last_file = Eden::LoadLastGame();
    if (!last_file.empty() && std::find(artwork_files.begin(), artwork_files.end(), last_file) == artwork_files.end())
        artwork_files.insert(artwork_files.begin(), last_file);
    for (const auto& entry : entries) {
        const std::string file = entry.path().filename().string();
        const std::size_t dot = file.find_last_of('.');
        if (file == "." || file == ".." || dot == std::string::npos) continue;
        std::string format = file.substr(dot + 1);
        std::transform(format.begin(), format.end(), format.begin(),
                       [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
        if (format != "NSP" && format != "XCI") continue;
        const std::string path = Eden::AssetsPath("roms/" + file);
        struct stat info {};
        if (stat(path.c_str(), &info) != 0 || !S_ISREG(info.st_mode)) continue;
        char size[32];
        const double bytes = static_cast<double>(info.st_size);
        if (bytes >= 1073741824.0) std::snprintf(size, sizeof(size), "%.1f GB", bytes / 1073741824.0);
        else std::snprintf(size, sizeof(size), "%.1f MB", bytes / 1048576.0);
        pe::ui::Game game;
        game.name = CleanTitle(file);
        game.format = format;
        game.size = size;
        game.file = file;
        // A game whose data cannot be read is still listed, by its file name.
        try {
            char title[513]{};
            // The cover is replaced in one step: the menu may be loading the old one right now.
            const std::string cover = CoverPath(file);
            const std::string staged = cover + ".new";
            const int metadata = eden_extract_game_metadata(path.c_str(), Eden::AssetsPath("keys").c_str(),
                                                            staged.c_str(), title, sizeof(title));
            if (metadata & EDEN_METADATA_TITLE) {
                game.name = title;
                SaveTitle(file, game.name);
            }
            if ((metadata & EDEN_METADATA_COVER) && std::rename(staged.c_str(), cover.c_str()) == 0)
                game.cover = cover;
            else
                (void)std::remove(staged.c_str());
            game.title_id = ResolveTitleId(path, file);
            if (game.title_id != 0 &&
                std::find(artwork_files.begin(), artwork_files.end(), file) != artwork_files.end())
                game.hero = CachedNlibHero(game.title_id);
            if (game.title_id != 0 &&
                std::find(artwork_files.begin(), artwork_files.end(), file) != artwork_files.end())
                game.max_players = CachedNlibPlayers(game.title_id);
            const GameLanguage language = LanguageFor(path, game.title_id, language_choice);
            game.addons = AddOnSummary(game.title_id);
            game.addons_short = AddOnSummary(game.title_id, true);
            game.language = language.label;
            game.language_note = language.note;
        } catch (const std::exception& error) {
            Eden::Report("library", (file + ": " + error.what()).c_str());
        }
        games.push_back(std::move(game));
    }

    // Metadata bridge work is finished. Do not hold it across network I/O: Nlib enrichment is
    // optional, bounded to the Home games, and runs in parallel so a slow network costs one timeout
    // rather than one timeout per game.
    lock.unlock();
    std::vector<std::pair<std::size_t, std::future<NlibEnrichment>>> artwork_tasks;
    for (std::size_t i = 0; i < games.size(); ++i) {
        auto& game = games[i];
        if (game.title_id == 0 ||
            (game.hero.empty() == false && game.max_players > 0) ||
            std::find(artwork_files.begin(), artwork_files.end(), game.file) == artwork_files.end())
            continue;
        const std::uint64_t title_id = game.title_id;
        artwork_tasks.emplace_back(i, std::async(std::launch::async, [title_id] {
            return EnsureNlibEnrichment(title_id);
        }));
    }
    for (auto& [index, task] : artwork_tasks) {
        NlibEnrichment enrichment = task.get();
        games[index].hero = std::move(enrichment.hero);
        games[index].max_players = enrichment.max_players;
    }

    std::sort(games.begin(), games.end(),
              [](const pe::ui::Game& a, const pe::ui::Game& b) { return a.name < b.name; });
    return games;
}

std::string EdenServices::game_path(const std::string& file) { return Eden::AssetsPath("roms/" + file); }

bool EdenServices::game_exists(const std::string& file) {
    return Eden::ValidRomFilename(file) && IsFile(Eden::AssetsPath("roms/" + file));
}

void EdenServices::arm_safe_launch() {
    // Same process: main.cpp consumes and unsets this before applying the game's settings.
    setenv("EDEN_SAFE_LAUNCH", "1", 1);
    Eden::Report("launch", "Safe launch armed for the next game only");
}

bool EdenServices::docked(std::uint64_t title_id) { return Eden::LoadGameDocked(title_id); }

bool EdenServices::set_docked(std::uint64_t title_id, bool docked) {
    return Eden::SaveGameDocked(title_id, docked);
}

pe::ui::GameSettings EdenServices::game_settings(std::uint64_t title_id) {
    const Eden::GameSettings saved = Eden::LoadGameSettings(title_id);
    pe::ui::GameSettings result;
    result.renderer = saved.renderer;
    result.output = saved.output;
    result.resolution = saved.resolution;
    result.filter = saved.upscaling_filter;
    result.fsr_sharpness = saved.fsr_sharpness;
    result.anti_aliasing = saved.anti_aliasing;
    result.refresh = saved.refresh;
    result.performance_profile = saved.performance_profile;
    result.controller_layout = saved.controller_layout;
    result.own_mapping = saved.own_mapping;
    result.mapping = saved.mapping;
    return result;
}

bool EdenServices::set_game_settings(std::uint64_t title_id, const pe::ui::GameSettings& settings) {
    Eden::GameSettings value;
    value.renderer = settings.renderer;
    value.output = settings.output;
    value.resolution = settings.resolution;
    value.upscaling_filter = settings.filter;
    value.fsr_sharpness = settings.fsr_sharpness;
    value.anti_aliasing = settings.anti_aliasing;
    value.refresh = settings.refresh;
    value.performance_profile = settings.performance_profile;
    value.controller_layout = settings.controller_layout;
    value.own_mapping = settings.own_mapping;
    value.mapping = settings.mapping;
    const bool saved = Eden::SaveGameSettings(title_id, value);
    if (!saved) Eden::Report("settings", "Could not write game settings");
    return saved;
}

pe::ui::Preferences EdenServices::preferences() {
    const Eden::Preferences saved = Eden::LoadPreferences();
    pe::ui::Preferences result;
    result.hud = saved.hud;
    result.volume = saved.volume;
    result.mute = saved.mute;
    result.detailed_logging = saved.detailed_logging;
    result.renderer = saved.backend == Eden::GraphicsBackend::OpenGL ? 0 : 1;
    result.resolution = saved.resolution;
    result.filter = saved.upscaling_filter;
    result.refresh = saved.refresh;
    result.output = saved.output;
    result.performance_profile = saved.performance_profile;
    result.controller_layout = saved.controller_layout;
    result.mapping = saved.mapping;
    result.vibration = saved.vibration;
    result.vibration_strength = saved.vibration_strength;
    result.stick_deadzone = saved.stick_deadzone;
    result.language = saved.language;
    result.menu_volume = saved.menu_volume;
    result.large_text = saved.large_text;
    result.high_contrast = saved.high_contrast;
    result.reduce_motion = saved.reduce_motion;
    return result;
}

bool EdenServices::set_preferences(const pe::ui::Preferences& preferences) {
    Eden::Preferences value;
    value.hud = preferences.hud;
    value.volume = preferences.volume;
    value.mute = preferences.mute;
    value.detailed_logging = preferences.detailed_logging;
    value.backend = preferences.renderer == 0 ? Eden::GraphicsBackend::OpenGL : Eden::GraphicsBackend::Vulkan;
    value.resolution = preferences.resolution;
    value.upscaling_filter = preferences.filter;
    value.fsr_sharpness = preferences.fsr_sharpness;
    value.anti_aliasing = preferences.anti_aliasing;
    value.refresh = preferences.refresh;
    value.output = preferences.output;
    value.performance_profile = preferences.performance_profile;
    value.controller_layout = preferences.controller_layout;
    value.mapping = preferences.mapping;
    value.vibration = preferences.vibration;
    value.vibration_strength = preferences.vibration_strength;
    value.stick_deadzone = preferences.stick_deadzone;
    value.language = preferences.language;
    value.menu_volume = preferences.menu_volume;
    value.large_text = preferences.large_text;
    value.high_contrast = preferences.high_contrast;
    value.reduce_motion = preferences.reduce_motion;
    const bool saved = Eden::SavePreferences(value);
    if (!saved) Eden::Report("settings", "Could not write preferences");
    return saved;
}

const std::vector<std::string>& EdenServices::resolution_labels() {
    return resolution_labels_;
}

const std::vector<std::string>& EdenServices::resolution_keys() {
    return resolution_keys_;
}

const std::vector<std::string>& EdenServices::filter_labels() {
    return filter_labels_;
}

const std::vector<std::string>& EdenServices::anti_aliasing_labels() {
    return anti_aliasing_labels_;
}

const std::vector<std::string>& EdenServices::performance_profile_labels() {
    return performance_profile_labels_;
}

const std::vector<std::string>& EdenServices::language_labels() {
    return language_labels_;
}

std::string EdenServices::language_region(int language) {
    static constexpr const char* kRegions[] = {TR("Japan"), TR("USA"), TR("Europe"), TR("Australia"), TR("China"),
                                               TR("Korea"), TR("Taiwan")};
    if (language < 0 || language >= int(std::size(Eden::kLanguageRegions))) return {};
    return tr(kRegions[Eden::kLanguageRegions[language]]);
}

std::string EdenServices::setup_details() {
    return setup_.empty() ?
        tr("Keys and firmware: startup checks passed. Game-specific compatibility is checked at launch.") :
        SetupMessage(setup_);
}

pe::ui::DiagnosticsInfo EdenServices::diagnostics() {
    pe::ui::DiagnosticsInfo result;
    result.filesystem = Eden::FilesystemAccess() ? tr("Full filesystem") : tr("Sandbox only");
    result.data_path = Eden::FilesystemAccess() ? Eden::kDataDir : Eden::UserDir();

    std::error_code error;
    const auto space = std::filesystem::space(Eden::UserDir(), error);
    result.free_space = error ? tr("Unknown") : StorageSize(space.available);
    result.total_space = error ? tr("Unknown") : StorageSize(space.capacity);
    if (!error) {
        result.free_bytes = static_cast<std::uint64_t>(space.available);
        result.total_bytes = static_cast<std::uint64_t>(space.capacity);
    }

    const std::filesystem::path cache = std::filesystem::path{Eden::UserDir()} / "cache";
    const std::uintmax_t shader_bytes =
        TreeBytes(cache / "shader") + TreeBytes(cache / "radv") +
        TreeBytes(cache / "native-opengl") + TreeBytes(cache / "jit");
    result.shader_cache_bytes = static_cast<std::uint64_t>(shader_bytes);
    result.shader_caches = StorageSize(shader_bytes);
    result.logs = StorageSize(TreeBytes(Eden::LogsDir()));
    return result;
}

bool EdenServices::clear_shader_caches(std::string* message) {
    const std::filesystem::path cache = std::filesystem::path{Eden::UserDir()} / "cache";
    const std::uintmax_t before =
        TreeBytes(cache / "shader") + TreeBytes(cache / "radv") +
        TreeBytes(cache / "native-opengl") + TreeBytes(cache / "jit");
    bool ok = true;
    // Eden's per-title Vulkan/OpenGL pipeline cache lives under cache/shader. The other
    // directories are backend/JIT auxiliaries. A maintenance clear must remove all of them,
    // otherwise the launcher can report success while the active game's pipelines survive.
    for (const char* name : {"shader", "radv", "native-opengl", "jit"}) {
        std::error_code error;
        std::filesystem::remove_all(cache / name, error);
        ok = ok && !error;
    }
    if (message) {
        if (ok)
            *message = fill(tr("Cleared {0} of shader/JIT caches."), {StorageSize(before)});
        else
            *message = tr("Some cache files could not be removed.");
    }
    if (ok) Eden::Report("cache", "Shader/JIT caches cleared from Diagnostics");
    return ok;
}

bool EdenServices::folders(const std::string& directory, std::vector<std::string>* names) {
    bool ok = false;
    *names = ListEntries(directory, true, ok);
    return ok;
}

pe::ui::FolderInfo EdenServices::folder_info(const std::string& directory) {
    pe::ui::FolderInfo info;
    info.keys = Eden::FileExists(JoinPath(directory, "keys/prod.keys"));
    info.firmware = CountFiles(JoinPath(directory, "firmware"), {".nca"});
    info.games = CountFiles(JoinPath(directory, "roms"), {".nsp", ".xci"});
    return info;
}

std::string EdenServices::files_folder() { return Eden::AssetsDir(); }
std::string EdenServices::saved_files_folder() { return Eden::LoadSavedAssetsDir(); }
std::string EdenServices::default_files_folder() { return Eden::kDefaultAssetsDir; }

bool EdenServices::set_files_folder(const std::string& directory) {
    if (!Eden::FilesystemAccess() || !Eden::ValidAssetsDir(directory)) return false;

    std::error_code error;
    const auto status = std::filesystem::symlink_status(directory, error);
    if (error || std::filesystem::is_symlink(status) || !std::filesystem::is_directory(status))
        return false;

    // Selecting external storage changes only the root. Every root has the exact same Encore
    // layout; individual keys/firmware/roms/etc. paths are never configurable.
    for (const char* name : {"keys", "firmware", "roms", "updates", "mods",
                             "save-import", "save-export", "ryujinx"}) {
        const std::filesystem::path child = std::filesystem::path{directory} / name;
        error.clear();
        const auto child_status = std::filesystem::symlink_status(child, error);
        if (!error && std::filesystem::exists(child_status) &&
            (std::filesystem::is_symlink(child_status) || !std::filesystem::is_directory(child_status))) {
            Eden::Report("storage", (std::string{"Unsafe storage entry: "} + child.string()).c_str());
            return false;
        }
        error.clear();
        std::filesystem::create_directories(child, error);
        if (error) {
            Eden::Report("storage", (std::string{"Could not prepare "} + name + ": " + error.message()).c_str());
            return false;
        }
    }
    const bool saved = Eden::SaveAssetsDir(directory);
    if (!saved) Eden::Report("settings", "Could not write the storage root");
    return saved;
}

int EdenServices::filesystem_access() { return Eden::FilesystemAccessStatus(); }

#ifdef EDEN_SAVE_IMPORT
// Save transfer (ryujinx_saves.h): a save comes in from save-import/<title ID>/ or a Ryujinx data
// folder in ryujinx/, and goes out to save-export/, all next to roms/.
bool EdenServices::save_transfer_available() { return true; }

pe::ui::SaveSource EdenServices::save_import_source(std::uint64_t title_id) {
    switch (eden_save_import_source(title_id)) {
    case EDEN_SAVE_FOLDER: return pe::ui::SaveSource::folder;
    case EDEN_SAVE_RYUJINX: return pe::ui::SaveSource::ryujinx;
    default: return pe::ui::SaveSource::none;
    }
}

bool EdenServices::save_import(std::uint64_t title_id, std::string* message) {
    char backup[256]{};
    switch (eden_save_import(title_id, backup, sizeof(backup))) {
    case EDEN_SAVE_DONE:
        *message = backup[0] ? tr("Imported. The save it replaced was backed up.") : tr("Imported.");
        return true;
    case EDEN_SAVE_NOTHING: {
        char title[17]{};
        std::snprintf(title, sizeof(title), "%016llX", static_cast<unsigned long long>(title_id));
        *message = fill(tr("To import, copy a Ryujinx folder to ryujinx/ or a save to save-import/{0}/, next to roms/."),
                        {title});
        return false;
    }
    case EDEN_SAVE_NO_USER:
        *message = tr("Start any game once before importing a save.");
        return false;
    default:
        *message = tr("Import failed. The current save is unchanged.");
        return false;
    }
}

bool EdenServices::save_export(std::uint64_t title_id, std::string* message) {
    char folder[256]{};
    switch (eden_save_export(title_id, folder, sizeof(folder))) {
    case EDEN_SAVE_DONE: {
        // The end of the path tells it apart: save-export/<title ID>-<date>-<time>.
        const std::string path = folder;
        const std::size_t name = path.rfind("save-export/");
        *message = fill(tr("Exported to {0}."), {name == std::string::npos ? path : path.substr(name)});
        return true;
    }
    case EDEN_SAVE_NOTHING:
        *message = tr("This game has no save to export yet.");
        return false;
    default:
        *message = tr("Export failed. Check that the storage root can be written.");
        return false;
    }
}
#else
bool EdenServices::save_transfer_available() { return false; }
pe::ui::SaveSource EdenServices::save_import_source(std::uint64_t) { return pe::ui::SaveSource::none; }
bool EdenServices::save_import(std::uint64_t, std::string*) { return false; }
bool EdenServices::save_export(std::uint64_t, std::string*) { return false; }
#endif

// Mods (headless/mods.h): what the selected storage root's mods/<title ID>/ holds for a game, and
// which of them are switched off (settings_store.h).
std::vector<pe::ui::Mod> EdenServices::mods(std::uint64_t title_id) {
    std::vector<pe::ui::Mod> result;
    const auto off = Eden::LoadDisabledMods(title_id);
    for (const Eden::Mods::Mod& mod : Eden::Mods::List(Eden::AssetsPath("mods"), title_id)) {
        std::string kind;
        const auto add = [&kind](const char* text) {
            if (!kind.empty()) kind += ", ";
            kind += tr(text);
        };
        if (mod.kinds & Eden::Mods::kCode) add(TR("Patch"));
        if (mod.kinds & Eden::Mods::kFiles) add(TR("Files"));
        if (mod.kinds & Eden::Mods::kCheats) add(TR("Cheats"));
        result.push_back({mod.name, kind, std::find(off.begin(), off.end(), mod.name) == off.end()});
    }
    return result;
}

bool EdenServices::set_mod_enabled(std::uint64_t title_id, const std::string& name, bool enabled) {
    const bool saved = Eden::SaveModEnabled(title_id, name, enabled);
    if (!saved) Eden::Report("settings", "Could not write the game's mods");
    return saved;
}

bool EdenServices::mods_enabled(std::uint64_t title_id) { return Eden::LoadModsEnabled(title_id); }

bool EdenServices::set_mods_enabled(std::uint64_t title_id, bool enabled) {
    const bool saved = Eden::SaveModsEnabled(title_id, enabled);
    if (!saved) Eden::Report("settings", "Could not write the game's mods switch");
    return saved;
}

std::string EdenServices::mods_folder(std::uint64_t title_id) {
    return "mods/" + Eden::Mods::TitleName(title_id) + "/";
}

bool EdenServices::make_mods_folder(std::uint64_t title_id) {
    const std::string root = Eden::AssetsPath("mods");
    if (!Eden::Mods::TitleFolder(root, title_id).empty()) return true;
    (void)mkdir(root.c_str(), 0777);
    return mkdir(Eden::Mods::TitleFolderToCreate(root, title_id).c_str(), 0777) == 0;
}

bool EdenServices::load_image(const std::string& path, pe::gfx::Image* image) {
    // Covers have full paths; the launcher's own art is named from its ui folder.
    return pe::gfx::load_tga(!path.empty() && path[0] == '/' ? path : Eden::AppFile("ui/" + path), image);
}
