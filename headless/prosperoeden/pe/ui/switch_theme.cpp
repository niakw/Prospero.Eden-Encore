// Eden Encore - optional console-style launcher presentation.
// Layout inspired by SwitchPS5 (kasobos67) and classic console HOME menus.
// Original vector UI only: no extracted firmware assets, fonts or sounds.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "pe/ui/launcher.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <string>

namespace pe::ui {
namespace {
const gfx::Color kPaper = gfx::Color::rgb(0xf7f7f7);
const gfx::Color kInk = gfx::Color::rgb(0x292929);
const gfx::Color kSubtle = gfx::Color::rgb(0x707070);
const gfx::Color kGrey = gfx::Color::rgb(0xd5d5d5);
const gfx::Color kFocus = gfx::Color::rgb(0x11b6d4);
const gfx::Color kWhite = gfx::Color::rgb(0xffffff);
const gfx::Color kBlack = gfx::Color::rgb(0x161616);
constexpr int kHomeGameSlots = 6;
constexpr int kHomeAllSoftware = 6;
constexpr int kHomeShortcutFirst = 7;
constexpr int kHomeShortcuts = 4;
constexpr int kLibraryColumns = 6;
constexpr int kLibraryPageSize = 18;

int switch_recent_count(const Home& home) {
    return std::min<int>(kHomeGameSlots, static_cast<int>(home.recents.size()));
}
void outline(gfx::DrawList& list, Rect r, bool selected, float radius = 3.0f) {
    if (selected) {
        list.shadow({r.x-3.0f,r.y-3.0f,r.w+6.0f,r.h+6.0f},radius,15.0f,
                    kFocus.with_alpha(0.25f));
        list.bordered_rect({r.x-5.0f,r.y-5.0f,r.w+10.0f,r.h+10.0f},
                           radius+2.0f, kPaper.with_alpha(0.0f), 5.0f, kFocus);
    } else {
        list.bordered_rect(r,radius,kPaper.with_alpha(0.0f),1.0f,kGrey);
    }
}
void action_circle(Canvas& c, float x, float y, int type, bool focus) {
    const std::array<gfx::Color,4> colors{
        gfx::Color::rgb(0x19b9d1), gfx::Color::rgb(0x7a7a7a),
        gfx::Color::rgb(0xe2a33d), gfx::Color::rgb(0x868686)};
    c.list.rounded_rect({x-36.0f,y-36.0f,72.0f,72.0f},36.0f,
                        colors[static_cast<std::size_t>(type)]);
    if (focus) c.list.ring(x,y,43.0f,4.0f,kFocus);
    switch(type) {
    case 0: // All software: original grid
        for (int a=0;a<2;++a) for(int b=0;b<2;++b)
            c.list.rounded_rect({x-19.0f+float(a)*22.0f,y-19.0f+float(b)*22.0f,
                                 16.0f,16.0f},2.0f,kWhite);
        break;
    case 1: // Controller-shaped symbol
        c.list.rounded_rect({x-26.0f,y-12.0f,52.0f,29.0f},14.0f,kWhite);
        c.list.rounded_rect({x-15.0f,y-6.0f,4.0f,16.0f},0.0f,kSubtle);
        c.list.rounded_rect({x-21.0f,y,16.0f,4.0f},0.0f,kSubtle);
        c.list.ring(x+15.0f,y-1.0f,3.0f,3.0f,kSubtle);
        break;
    case 2: // Data folder
        c.list.rounded_rect({x-24.0f,y-16.0f,48.0f,34.0f},5.0f,kWhite);
        c.list.rounded_rect({x-21.0f,y-22.0f,22.0f,11.0f},3.0f,kWhite);
        break;
    case 3: // System settings
        for (int a=0;a<8;++a) {
            const float theta=float(a)*3.14159265f/4.0f;
            c.list.rounded_rect({x+std::cos(theta)*23.0f-5.0f,
                                 y+std::sin(theta)*23.0f-5.0f,10.0f,10.0f},
                                 2.0f,kWhite);
        }
        c.list.ring(x,y,17.0f,7.0f,kWhite);
        break;
    }
}
} // namespace

void Launcher::draw_switch_header(Canvas& c, const char *heading) {
    auto& list=c.list;
    list.rounded_rect({0.0f,0.0f,1920.0f,1080.0f},0.0f,kPaper);
    text_shrink(c,heading,99.0f,baseline(70.0f,62.0f,33.0f),
                33.0f,kInk,1280.0f);
    // Active account remains native and read-only, identical to Encore mode.
    constexpr float px=1652.0f,py=101.0f;
    const Cover avatar=profile_avatar_path_.empty()?Cover{}:
        textures_.cover(profile_avatar_path_,52.0f);
    if(avatar.texture) {
        Rect uv{0,0,1,1};
        const float aspect=std::max(0.01f,avatar.aspect);
        if(aspect>1){uv.w=1/aspect;uv.x=(1-uv.w)*.5f;}
        if(aspect<1){uv.h=aspect;uv.y=(1-uv.h)*.5f;}
        list.rounded_image(avatar.texture,{px-23,py-23,46,46},uv,23,kWhite);
    } else {
        list.rounded_rect({px-24,py-24,48,48},24,kGrey);
        list.ring(px,py-6,9,4,kWhite);
        list.rounded_rect({px-14,py+8,28,11},6,kWhite);
    }
    text(c,clock_,1835.0f,baseline(81.0f,42.0f,24.0f),24.0f,kInk,Align::right);
}

void Launcher::draw_switch_footer(Canvas& c,const char *hint) {
    c.list.rounded_rect({92,979,1736,2},0,kGrey);
    text_shrink(c,hint,110.0f,baseline(993.0f,49.0f,20.0f),20,kSubtle,1250.0f);
    text(c,tr("Back"),1670.0f,baseline(993.0f,49.0f,21.0f),21,kInk,Align::right);
    c.list.ring(1549,1017,13,2,kSubtle);
    text(c,tr("Select"),1805.0f,baseline(993.0f,49.0f,21.0f),21,kInk,Align::right);
    c.list.ring(1691,1017,13,2,kSubtle);
}

void Launcher::draw_switch_home(Canvas& c) {
    draw_switch_header(c,"");
    auto& list=c.list;
    const int count=switch_recent_count(home_);
    const int focus=std::clamp(switch_home_focus_,0,kHomeShortcutFirst+kHomeShortcuts-1);
    const float tile=252.0f,pitch=276.0f,start=90.0f,top=336.0f;
    const char *placeholder=tr("All Software");
    for(int i=0;i<count;++i){
        const auto& g=home_.recents[static_cast<std::size_t>(i)];
        const Rect r{start+float(i)*pitch,top,tile,tile};
        if(!g.cover.empty())cover_crop(c,g.cover,r,0.0f,0.0f);
        else {
            list.rounded_rect(r,1.0f,gfx::Color::rgb(0x343c49));
            text_shrink(c,g.title,r.x+tile*.5f,
                baseline(r.y+64.0f,120.0f,25.0f),25,kWhite,tile-30,Align::center);
        }
        outline(list,r,focus==i,0.0f);
    }
    // A dedicated All Software tile, positioned immediately after recents.
    const int allIndex=count;
    const Rect all{start+float(allIndex)*pitch,top,tile,tile};
    list.rounded_rect(all,0.0f,gfx::Color::rgb(0x17aacc));
    for(int a=0;a<3;++a)for(int b=0;b<3;++b)
        list.rounded_rect({all.x+77+float(a)*37,all.y+73+float(b)*37,24,24},2.0f,kWhite);
    outline(list,all,focus==kHomeAllSoftware,0.0f);
    const bool highlighted=focus<count||focus==kHomeAllSoftware;
    if(highlighted) {
        const std::string name=focus==kHomeAllSoftware?placeholder:
            home_.recents[static_cast<std::size_t>(focus)].title;
        text_shrink(c,name,100.0f,baseline(256.0f,51.0f,31.0f),
                    31,kInk,1600.0f);
    }
    const char *shortcuts[kHomeShortcuts]={TR("All Software"),TR("Controllers"),
                                         TR("Game files"),TR("System Settings")};
    constexpr float sx=540.0f,step=210.0f,sy=824.0f;
    for(int i=0;i<kHomeShortcuts;++i) {
        const float cx=sx+float(i)*step;
        action_circle(c,cx,sy,i,focus==kHomeShortcutFirst+i);
        text_shrink(c,tr(shortcuts[i]),cx,baseline(867.0f,39.0f,18.0f),
                    18,kInk,198,Align::center);
    }
    draw_switch_footer(c,tr("Choose software or a system function"));
}

void Launcher::press_switch_home(Key key) {
    const int count=switch_recent_count(home_);
    const int current=std::clamp(switch_home_focus_,0,kHomeShortcutFirst+kHomeShortcuts-1);
    switch(key) {
    case Key::left:
    case Key::right: {
        const int delta=key==Key::right?1:-1;
        if(current>=kHomeShortcutFirst) {
            switch_home_focus_=kHomeShortcutFirst+
                (current-kHomeShortcutFirst+delta+kHomeShortcuts)%kHomeShortcuts;
        } else {
            const int position=current==kHomeAllSoftware?count:std::min(current,count);
            const int next=(position+delta+count+1)%(count+1);
            switch_home_focus_=next==count?kHomeAllSoftware:next;
        }
        cue(Cue::focus);return;
    }
    case Key::down:
        switch_home_focus_=kHomeShortcutFirst;
        cue(Cue::focus);return;
    case Key::up:
        switch_home_focus_=kHomeAllSoftware;
        cue(Cue::focus);return;
    case Key::circle:
        (void)confirm_action(Confirmation::exit_app);return;
    case Key::triangle:
        if(current<count && home_.setup_ready)
            (void)open_game_settings_at_file(home_.recents[static_cast<std::size_t>(current)].file);
        return;
    case Key::cross:
        if(current<count) {
            const auto& g=home_.recents[static_cast<std::size_t>(current)];
            if(home_.setup_ready && services_.game_exists(g.file))
                launch(g.file,g.title,g.cover);
            else cue(Cue::error);
        } else if(current==kHomeAllSoftware||current==kHomeShortcutFirst) {
            open(Screen::library,true);enter_library();
        } else if(current==kHomeShortcutFirst+1) {
            open_mapping(false);
        } else if(current==kHomeShortcutFirst+2) {
            open(Screen::files,true);enter_files();
        } else if(current==kHomeShortcutFirst+3) {
            open(Screen::settings,true);prefs_=services_.preferences();section_.snap(1.0f);
        }
        return;
    default:return;
    }
}

void Launcher::draw_switch_library(Canvas& c) {
    draw_switch_header(c,tr("All Software"));
    auto& list=c.list;
    const int count=static_cast<int>(games_.size());
    if(count==0) {
        text_shrink(c,tr("No ROM files found."),960.0f,baseline(440,80,30),
                    30,kInk,1300,Align::center);
        draw_switch_footer(c,tr("Back to HOME"));return;
    }
    const int selected=std::clamp(library_.selected,0,count-1);
    const int start=(selected/kLibraryPageSize)*kLibraryPageSize;
    constexpr float tile=232.0f,gap=31.0f,x0=120.0f,y0=236.0f;
    for(int pos=start;pos<std::min(count,start+kLibraryPageSize);++pos){
        const auto& g=games_[static_cast<std::size_t>(pos)];
        const int local=pos-start,col=local%kLibraryColumns,row=local/kLibraryColumns;
        const Rect r{x0+float(col)*(tile+gap),y0+float(row)*(tile+gap),tile,tile};
        if(!g.cover.empty())cover_crop(c,g.cover,r,0.0f);
        else if(!g.box_front.empty())cover_crop(c,g.box_front,r,0.0f);
        else {
            list.rounded_rect(r,0.0f,gfx::Color::rgb(0x415169));
            text_shrink(c,g.name,r.x+tile*.5f,
                        baseline(r.y+53,120,23),23,kWhite,tile-28,Align::center);
        }
        outline(list,r,pos==selected,0.0f);
    }
    const Game& game=games_[static_cast<std::size_t>(selected)];
    text_shrink(c,game.name,125.0f,baseline(150,55,29),29,kInk,1420.0f);
    text(c,list_position(selected+1,count),1790.0f,baseline(152,50,21),
         21,kSubtle,Align::right);
    draw_switch_footer(c,tr("Software options: Triangle"));
}

void Launcher::press_switch_library(Key key) {
    const int count=static_cast<int>(games_.size());
    if(key==Key::circle) {open(Screen::home,false);return;}
    if(count==0) {if(key==Key::cross)cue(Cue::error);return;}
    const int current=std::clamp(library_.selected,0,count-1);
    int next=current;
    switch(key) {
    case Key::left:next=std::max(0,current-1);break;
    case Key::right:next=std::min(count-1,current+1);break;
    case Key::up:next=std::max(0,current-kLibraryColumns);break;
    case Key::down:next=std::min(count-1,current+kLibraryColumns);break;
    case Key::l1:next=std::max(0,current-kLibraryPageSize);break;
    case Key::r1:next=std::min(count-1,current+kLibraryPageSize);break;
    case Key::cross: {
        const auto& g=games_[static_cast<std::size_t>(current)];
        launch(g.file,g.name,g.cover);return;
    }
    case Key::triangle:
    case Key::square:
    case Key::options:
        press_library(key);return;
    default:return;
    }
    if(next!=current) {
        library_.reset(count,next);
        refresh_selected_game();
        mode_.snap(selected_docked_?0.0f:1.0f);
        cue(Cue::focus);
    }
}

void Launcher::draw_switch_settings(Canvas& c) {
    draw_switch_header(c,tr("System Settings"));
    auto& list=c.list;
    static constexpr const char *categories[]={
        TR("Video"),TR("Audio"),TR("Controls"),TR("Accessibility"),
        TR("Appearance"),TR("Diagnostics"),TR("Storage"),TR("Language")};
    constexpr int n=8;
    const int selected=std::clamp(settings_.selected,0,n-1);
    list.rounded_rect({92,173,1736,1},0,kGrey);
    list.rounded_rect({608,175,2,755},0,kGrey);
    for(int i=0;i<n;++i) {
        const Rect r{98.0f,194.0f+float(i)*87.0f,493.0f,77.0f};
        if(i==selected)list.rounded_rect(r,3.0f,kFocus);
        text_shrink(c,tr(categories[i]),r.x+26,baseline(r.y,77,25),
                    25,i==selected?kWhite:kInk,r.w-48);
    }
    const char* title=tr(categories[selected]);
    text_shrink(c,title,675.0f,baseline(211.0f,58.0f,34.0f),
                34,kInk,1060.0f);
    list.rounded_rect({674,287,1096,2},0,kGrey);
    struct Line {const char* name;std::string value;};
    std::array<Line,4> rows{};
    int size=0;
    switch(selected) {
    case 0:
        rows={Line{TR("Renderer"),prefs_.renderer?"Vulkan":"OpenGL"},
              Line{TR("TV output"),prefs_.output==2?"2160p":prefs_.output==1?"1440p":"1080p"},
              Line{TR("FPS overlay"),prefs_.hud?tr("On"):tr("Off")},Line{TR("Video preset"),tr("Configure")}};
        size=4;break;
    case 1:
        rows={Line{TR("Volume"),std::to_string(prefs_.volume)+"%"},
              Line{TR("Mute"),prefs_.mute?tr("On"):tr("Off")},Line{TR("Menu sounds"),std::to_string(prefs_.menu_volume)+"%"},Line{"",""}};
        size=3;break;
    case 2:
        rows={Line{TR("Controller profile"),prefs_.controller_layout?"Switch":"PlayStation"},
              Line{TR("Vibration"),prefs_.vibration?tr("On"):tr("Off")},Line{TR("Stick deadzone"),std::to_string(prefs_.stick_deadzone)+"%"},Line{"",""}};
        size=3;break;
    case 3:
        rows={Line{TR("Larger text"),prefs_.large_text?tr("On"):tr("Off")},
              Line{TR("High contrast"),prefs_.high_contrast?tr("On"):tr("Off")},
              Line{TR("Reduce motion"),prefs_.reduce_motion?tr("On"):tr("Off")},Line{"",""}};
        size=3;break;
    case 4:
        rows={Line{TR("Theme"),prefs_.ui_theme?"Switch":"Encore"},
              Line{TR("Original Encore interface"),prefs_.ui_theme?"":tr("Active")},
              Line{TR("Switch-style interface"),prefs_.ui_theme?tr("Active"):""},Line{"",""}};
        size=3;break;
    case 5:
        rows={Line{TR("Detailed logging"),prefs_.detailed_logging?tr("On"):tr("Off")},
              Line{TR("Cache"),tr("Manage")},Line{"",""},Line{"",""}};size=2;break;
    case 6:
        rows={Line{TR("Game files"),tr("Open folders")},Line{"",""},Line{"",""},Line{"",""}};size=1;break;
    case 7:
        rows={Line{TR("Language"),tr("Change")},Line{"",""},Line{"",""},Line{"",""}};size=1;break;
    }
    for(int i=0;i<size;++i){
        const float y=310.0f+float(i)*110.0f;
        text_shrink(c,tr(rows[static_cast<std::size_t>(i)].name),696,y+37,25,kInk,660);
        text_shrink(c,rows[static_cast<std::size_t>(i)].value,
                    1730.0f,y+37,24,kSubtle,450,Align::right);
        list.rounded_rect({696,y+72,1040,1},0,kGrey);
    }
    text_shrink(c,tr("Press Select to configure"),695.0f,baseline(811,50,20),
                20,kSubtle,920);
    draw_switch_footer(c,tr("Select a settings category"));
}

void Launcher::press_switch_settings(Key key) {
    if(key==Key::down||key==Key::up||key==Key::left||key==Key::right) {
        if(settings_.move(key==Key::down||key==Key::right?1:-1)) {
            section_.snap(1.0f);cue(Cue::focus);
            // Category Diagnostics performs its expensive scan off-thread.
            if(settings_.selected==5) start_diagnostics();
        }
        return;
    }
    // Preserve all native settings dialogs, language and storage behavior.
    press_settings(key);
}

} // namespace pe::ui
