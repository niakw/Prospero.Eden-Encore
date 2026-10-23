// Eden Encore - optional console-style launcher presentation.
// Layout inspired by SwitchPS5 (kasobos67) and classic console HOME menus.
// Original vector UI only: no extracted firmware assets, fonts or sounds.
// SPDX-License-Identifier: GPL-3.0-or-later
#include "pe/ui/launcher.hpp"
#include "pe/ui/video_presets.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <string>

namespace pe::ui {
using audio::Cue;
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
constexpr int kHomeShortcuts = 6;
constexpr int kLibraryColumns = 6;
constexpr int kLibraryPageSize = 18;
constexpr float kSwitchHomeTileSize = 384.0f;
constexpr float kSwitchHomeTilePitch = 405.0f;
constexpr float kSwitchHomeTileX = 160.5f;
constexpr float kSwitchHomeTileY = 291.0f;
constexpr float kSwitchLibraryTileSize = 261.0f;
constexpr float kSwitchLibraryTilePitch = 276.0f;
constexpr float kSwitchLibraryTileX = 138.0f;
constexpr float kSwitchLibraryTileY = 278.0f;

std::string switch_value(const std::vector<std::string>& values,int index) {
    return index>=0 && index<static_cast<int>(values.size()) ?
        values[static_cast<std::size_t>(index)] : std::string{"-"};
}
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
void switch_game_tile(Canvas& c,const std::string& path,const std::string& title,
                      const Rect& r,int ordinal) {
    // The art cache fills asynchronously. Never expose an empty black tile:
    // show a deliberate original vector illustration until genuine art arrives.
    const Cover image=path.empty()?Cover{}:c.textures.cover(path,std::max(r.w,r.h));
    if(image.texture!=0) {
        cover_crop(c,path,r,0.0f,0.0f);
        return;
    }
    static const std::array<gfx::Color,6> tops{
        gfx::Color::rgb(0x126e86),gfx::Color::rgb(0x523688),
        gfx::Color::rgb(0xb36b35),gfx::Color::rgb(0x235480),
        gfx::Color::rgb(0x7b365e),gfx::Color::rgb(0x367459)};
    static const std::array<gfx::Color,6> bottoms{
        gfx::Color::rgb(0x172c49),gfx::Color::rgb(0x1d244d),
        gfx::Color::rgb(0x482a39),gfx::Color::rgb(0x12283a),
        gfx::Color::rgb(0x352542),gfx::Color::rgb(0x18343a)};
    const std::size_t index=static_cast<std::size_t>((ordinal%6+6)%6);
    c.list.gradient_rect(r,0.0f,tops[index],bottoms[index]);
    // Sun and layered hills: purpose-drawn placeholder, not firmware artwork.
    c.list.ring(r.x+r.w*.65f,r.y+r.h*.30f,r.w*.115f,10.0f,
                kWhite.with_alpha(0.88f));
    c.list.rounded_rect({r.x,r.y+r.h*.66f,r.w,r.h*.34f},0.0f,
                        kBlack.with_alpha(0.30f));
    text_shrink(c,title,r.x+r.w*.5f,
                baseline(r.y+r.h*.68f,r.h*.28f,22.0f),22.0f,
                kWhite,r.w-26.0f,Align::center);
}
void action_circle(Canvas& c, float x, float y, int type, bool focus) {
    // Geometry follows the reference console shell: 132 px circles, 162 px
    // centers, and 96-132 px ink. Artwork is authored as native vectors.
    static const std::array<gfx::Color,6> inks{
        gfx::Color::rgb(0xff4d4d),gfx::Color::rgb(0xffae2e),
        gfx::Color::rgb(0x4a9bdb),gfx::Color::rgb(0x666666),
        gfx::Color::rgb(0x555555),gfx::Color::rgb(0x555555)};
    const gfx::Color ink=inks[static_cast<std::size_t>(type)];
    c.list.rounded_rect({x-66,y-66,132,132},66,kWhite);
    c.list.ring(x,y,66,1.6f,kGrey);
    if(focus)c.list.ring(x,y,72,4,kFocus);
    switch(type) {
    case 0: { // News: a framed newspaper with headline and lines
        c.list.bordered_rect({x-37,y-35,74,70},6,
                             kWhite.with_alpha(0),6,ink);
        c.list.rounded_rect({x-28,y-24,28,27},3,ink);
        for(int i=0;i<3;++i)
            c.list.rounded_rect({x+8,y-22+float(i)*11,21,4},1,ink);
        c.list.rounded_rect({x-28,y+12,56,5},1,ink);
        c.list.rounded_rect({x-28,y+24,46,5},1,ink);
        break;
    }
    case 1: { // eShop-style bag, no borrowed emblem
        c.list.bordered_rect({x-34,y-24,68,68},4,
                             kWhite.with_alpha(0),6,ink);
        c.list.ring(x,y-29,14,5,ink);
        c.list.rounded_rect({x-21,y+8,42,6},2,ink);
        break;
    }
    case 2: { // Local multiplayer: two paired user circles
        c.list.ring(x-17,y-21,16,5,ink);
        c.list.ring(x+22,y-15,12,4,ink);
        c.list.rounded_rect({x-43,y+5,55,30},15,ink);
        c.list.rounded_rect({x+12,y+6,35,24},12,ink);
        break;
    }
    case 3: { // Pair of vertically split controller halves
        c.list.rounded_rect({x-37,y-45,32,88},17,ink);
        c.list.rounded_rect({x+5,y-45,32,88},17,ink);
        c.list.ring(x-21,y-12,8,3,kWhite);
        c.list.ring(x+21,y+13,8,3,kWhite);
        c.list.rounded_rect({x+16,y-17,10,10},5,kWhite);
        break;
    }
    case 4: { // Eight-tooth system gear with central bore
        for(int i=0;i<8;++i) {
            const float angle=3.1415926535f*float(i)/4.0f;
            c.list.rounded_rect({x+std::cos(angle)*35-9,
                                 y+std::sin(angle)*35-9,18,18},3,ink);
        }
        c.list.rounded_rect({x-33,y-33,66,66},29,ink);
        c.list.ring(x,y,14,9,kWhite);
        break;
    }
    case 5: { // Power glyph
        c.list.ring(x,y+4,33,8,ink);
        c.list.rounded_rect({x-10,y-45,20,47},10,kWhite);
        c.list.rounded_rect({x-5,y-43,10,37},4,ink);
        break;
    }
    }
}


constexpr Rect kAdvancedClip{530.0f,302.0f,861.0f,498.0f};
void advanced_panel(Canvas& c,const char* title,const std::string& subtitle) {
    auto& d=c.list;
    const Rect panel{467,124,986,831};
    d.shadow({453,111,1014,862},8,35,kBlack.with_alpha(.15f));
    d.rounded_rect(panel,5,kWhite);
    d.bordered_rect(panel,5,kWhite,1,kGrey);
    text_shrink(c,title,534,baseline(162,64,35),35,kInk,843);
    text_shrink(c,subtitle,535,baseline(224,52,22),22,kSubtle,838);
    d.rounded_rect({536,292,846,2},0,kGrey);
    d.rounded_rect({536,815,846,1},0,kGrey);
}
void advanced_row(Canvas& c,float top,bool focus,const std::string& key,
                  const std::string& value,float opacity=1.0f) {
    auto& d=c.list;
    d.push_opacity(opacity);
    const Rect r{541,top,832,92};
    if(focus) {
        d.rounded_rect(r,4,gfx::Color::rgb(0xe7faff));
        d.bordered_rect(r,4,kWhite.with_alpha(0),3,kFocus);
    } else d.rounded_rect({r.x+4,r.y+91,r.w-8,1},0,kGrey);
    text_shrink(c,key,r.x+24,baseline(top,92,23),23,kInk,423);
    text_shrink(c,value,r.x+r.w-22,baseline(top,92,22),
                22,focus?kInk:kSubtle,350,Align::right);
    d.pop_opacity();
}
void advanced_status(Canvas& c,const std::string& message,bool warn,
                     const char* fallback) {
    // An old confirmation may leave message_warning_ true even when
    // message_ is cleared. Ordinary actions must never inherit error red.
    // Leave the A/B controls unobstructed even for two-line translated
    // status messages (e.g. game-saved notifications in French).
    text_block(c,message.empty()?tr(fallback):message,544.0f,
               baseline(831.0f,39.0f,18.0f),18.0f,25.0f,
               !message.empty()&&warn?gfx::Color::rgb(0xb52733):kSubtle,
               418.0f,2,kShrink);
    // Keep the alternative console's A/B action grammar inside every
    // advanced modal, not just in the underlying HOME footer.
    c.list.ring(996.0f,877.0f,15.0f,2.0f,kSubtle);
    text(c,"A",996.0f,883.0f,18.0f,kInk,Align::center);
    text_shrink(c,tr("Select"),1024.0f,884.0f,20.0f,kInk,148.0f);
    c.list.ring(1202.0f,877.0f,15.0f,2.0f,kSubtle);
    text(c,"B",1202.0f,883.0f,18.0f,kInk,Align::center);
    text_shrink(c,tr("Back"),1230.0f,884.0f,20.0f,kInk,138.0f);
}
std::string switch_default(const std::string& value) {
    return fill(tr("Default ({0})"),{value});
}
std::string switch_profile_name(int layout,const ButtonMapping& mapping) {
    const bool custom=mapping_is_custom(mapping,layout);
    if(layout==1) return custom?tr("Custom Switch"):tr("Switch");
    return custom?tr("Custom PS5"):tr("PlayStation");
}
Pad switch_physical_pad(int pad) {
    static constexpr Pad icons[kPadButtons]={
        Pad::cross,Pad::circle,Pad::square,Pad::triangle,
        Pad::l1,Pad::r1,Pad::l2,Pad::r2,Pad::l3,Pad::r3,
        Pad::options,Pad::create,Pad::touchpad
    };
    return icons[static_cast<std::size_t>(std::clamp(pad,0,kPadButtons-1))];
}
std::string switch_pad_label(int p) {
    static const char* names[]={
        TR("Cross"),TR("Circle"),TR("Square"),TR("Triangle"),
        "L1","R1","L2","R2","L3","R3",TR("Options"),
        TR("Create"),TR("Touchpad")};
    return tr(names[std::clamp(p,0,12)]);
}

} // namespace

void Launcher::draw_switch_header(Canvas& c, const char *heading) {
    auto& list=c.list;
    list.rounded_rect({0.0f,0.0f,1920.0f,1080.0f},0.0f,kPaper);
    text_shrink(c,heading,99.0f,baseline(70.0f,62.0f,33.0f),
                33.0f,kInk,1280.0f);
    // The reference HOME alone has the account avatar in the top-left
    // corner. Secondary pages place their titles there instead.
    if(heading != nullptr && heading[0] == '\0') {
    // Active account remains native and read-only, identical to Encore mode.
    constexpr float px=136.5f,py=98.0f;
    const Cover avatar=profile_avatar_path_.empty()?Cover{}:
        textures_.cover(profile_avatar_path_,76.0f);
    if(avatar.texture) {
        Rect uv{0,0,1,1};
        const float aspect=std::max(0.01f,avatar.aspect);
        if(aspect>1){uv.w=1/aspect;uv.x=(1-uv.w)*.5f;}
        if(aspect<1){uv.h=aspect;uv.y=(1-uv.h)*.5f;}
        list.rounded_image(avatar.texture,{px-36,py-36,72,72},uv,36,kWhite);
    } else {
        list.rounded_rect({px-36,py-36,72,72},36,kGrey);
        list.ring(px,py-10,14,5,kWhite);
        list.rounded_rect({px-21,py+12,42,17},9,kWhite);
    }
    }
    text(c,clock_,1814.0f,baseline(80.0f,50.0f,30.0f),30.0f,kInk,Align::right);
}

void Launcher::draw_switch_footer(Canvas& c,const char *hint) {
    c.list.rounded_rect({92,979,1736,2},0,kGrey);
    text_shrink(c,hint,110.0f,baseline(993.0f,49.0f,20.0f),20,kSubtle,1250.0f);
    c.list.ring(1495.0f,1017.0f,14.0f,2.0f,kSubtle);
    text(c,"B",1495.0f,1023.0f,17.0f,kInk,Align::center);
    text_shrink(c,tr("Back"),1525.0f,1025.0f,19.0f,kInk,116.0f);
    c.list.ring(1690.0f,1017.0f,14.0f,2.0f,kSubtle);
    text(c,"A",1690.0f,1023.0f,17.0f,kInk,Align::center);
    text_shrink(c,tr("Select"),1720.0f,1025.0f,19.0f,kInk,170.0f);
}

void Launcher::draw_switch_home(Canvas& c) {
    draw_switch_header(c,"");
    auto& list=c.list;
    const int count=switch_recent_count(home_);
    const int focus=count==0 && switch_home_focus_<kHomeShortcutFirst ?
        kHomeAllSoftware : std::clamp(switch_home_focus_,0,kHomeShortcutFirst+kHomeShortcuts-1);
    const int target=focus==kHomeAllSoftware?count:std::min(focus,count);
    const float maxOffset=std::max(0.0f,
        kSwitchHomeTileX + float(count)*kSwitchHomeTilePitch
        + kSwitchHomeTileSize - 1778.0f);
    const float offset=std::clamp(
        kSwitchHomeTileX + float(target)*kSwitchHomeTilePitch
        + kSwitchHomeTileSize*0.5f - 960.0f,0.0f,maxOffset);
    const char* allTitle=tr("All Software");
    const std::string active=focus==kHomeAllSoftware?allTitle:
        focus<count?home_.recents[static_cast<std::size_t>(focus)].title:"";
    // text_shrink's center alignment uses x as the anchor, not the width.
    // Keep the selected software title directly above its tile, in bounds.
    const float titleCenter=std::clamp(
        kSwitchHomeTileX+float(target)*kSwitchHomeTilePitch+
        kSwitchHomeTileSize*0.5f-offset,410.0f,1510.0f);
    text_shrink(c,active,titleCenter,baseline(222.0f,52.0f,32.0f),
                32.0f,kInk,800.0f,Align::center);

    list.push_clip({0.0f,278.0f,1920.0f,426.0f});
    for(int i=0;i<count;++i) {
        const auto& item=home_.recents[static_cast<std::size_t>(i)];
        const Rect box{kSwitchHomeTileX+float(i)*kSwitchHomeTilePitch-offset,
                       kSwitchHomeTileY,kSwitchHomeTileSize,kSwitchHomeTileSize};
        switch_game_tile(c,item.cover,item.title,box,i);
        outline(list,box,focus==i,0.0f);
    }
    const Rect all{kSwitchHomeTileX+float(count)*kSwitchHomeTilePitch-offset,
                   kSwitchHomeTileY+72.0f,240.0f,240.0f};
    list.rounded_rect(all,120.0f,kWhite);
    list.ring(all.x+120.0f,all.y+120.0f,118.0f,2.0f,kGrey);
    for(int row=0;row<3;++row)for(int col=0;col<3;++col)
        list.rounded_rect({all.x+70.0f+float(col)*36.0f,
                           all.y+71.0f+float(row)*36.0f,25.0f,25.0f},
                          2.0f,kInk);
    outline(list,all,focus==kHomeAllSoftware,120.0f);
    list.pop_clip();

    // The reference has six HOME functions, centered at these exact x/y
    // coordinates in the native 1920x1080 coordinate space.
    const char* names[]={
        TR("About"),TR("Game files"),TR("Multiplayer"),
        TR("Controllers"),TR("System Settings"),TR("Exit Eden Encore")};
    for(int i=0;i<kHomeShortcuts;++i){
        const float x=555.0f+162.0f*float(i),y=816.0f;
        action_circle(c,x,y,i,focus==kHomeShortcutFirst+i);
        if(focus==kHomeShortcutFirst+i)
            text_shrink(c,tr(names[i]),x,baseline(892.0f,40.0f,24.0f),
                        24.0f,kInk,318.0f,Align::center);
    }
    // Preserve launch/permission feedback shown in the original launcher.
    const std::string feedback=!message_.empty()?message_:home_.status;
    if(modal_==Modal::none && confirmation_==Confirmation::none && !feedback.empty())
        text_shrink(c,feedback,165.0f,baseline(701.0f,46.0f,22.0f),
                    22.0f,!message_.empty()&&message_warning_?
                    gfx::Color::rgb(0xb52733):kSubtle,1585.0f);
    draw_switch_footer(c,"");
}

void Launcher::press_switch_home(Key key) {
    const int count=switch_recent_count(home_);
    const int current=count==0 && switch_home_focus_<kHomeShortcutFirst ?
        kHomeAllSoftware : std::clamp(switch_home_focus_,0,kHomeShortcutFirst+kHomeShortcuts-1);
    switch(key) {
    case Key::left:
    case Key::right: {
        const int delta=key==Key::right?1:-1;
        const int next=current>=kHomeShortcutFirst ?
            std::clamp(current+delta,kHomeShortcutFirst,
                       kHomeShortcutFirst+kHomeShortcuts-1) :
            std::clamp((current==kHomeAllSoftware?count:current)+delta,0,count);
        const int candidate=current>=kHomeShortcutFirst?next:
            next==count?kHomeAllSoftware:next;
        if(candidate==current)
            return; // native Encore sound table has no scroll-limit cue
        switch_home_focus_=candidate;
        if(candidate<=kHomeAllSoftware) switch_home_last_tile_=candidate;
        cue(Cue::focus);return;
    }
    case Key::down:
        if(current<kHomeShortcutFirst) {
            switch_home_last_tile_=current;
            switch_home_focus_=kHomeShortcutFirst;
            cue(Cue::focus);
        }
        return;
    case Key::up:
        if(current>=kHomeShortcutFirst) {
            const int last=std::clamp(switch_home_last_tile_,0,kHomeAllSoftware);
            switch_home_focus_=last==kHomeAllSoftware||last>=count?
                kHomeAllSoftware:last;
            cue(Cue::focus);
        }
        return;
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
        } else if(current==kHomeAllSoftware) {
            open(Screen::library,true);enter_library();
        } else if(current==kHomeShortcutFirst) {
            open(Screen::about,true);
        } else if(current==kHomeShortcutFirst+1) {
            open(Screen::files,true);enter_files();
        } else if(current==kHomeShortcutFirst+2) {
            // Online multiplayer is not supported by this port.
            cue(Cue::error);
        } else if(current==kHomeShortcutFirst+3) {
            open_mapping(false);
        } else if(current==kHomeShortcutFirst+4) {
            open(Screen::settings,true);prefs_=services_.preferences();section_.snap(1.0f);
        } else if(current==kHomeShortcutFirst+5) {
            (void)confirm_action(Confirmation::exit_app);
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
    // Three complete rows must end BEFORE the footer divider (y=979).
    constexpr float tile=kSwitchLibraryTileSize,gap=kSwitchLibraryTilePitch-kSwitchLibraryTileSize;
    constexpr float x0=kSwitchLibraryTileX,y0=kSwitchLibraryTileY;
    const float availableBottom=938.0f;
    const float selectedRow=float((selected%kLibraryPageSize)/kLibraryColumns);
    const float scroll=std::max(0.0f,
        y0+selectedRow*kSwitchLibraryTilePitch+tile-availableBottom);
    list.push_clip({70.0f,270.0f,1780.0f,670.0f});
    for(int pos=start;pos<std::min(count,start+kLibraryPageSize);++pos){
        const auto& g=games_[static_cast<std::size_t>(pos)];
        const int local=pos-start,col=local%kLibraryColumns,row=local/kLibraryColumns;
        const Rect r{x0+float(col)*(tile+gap),y0+float(row)*(tile+gap)-scroll,tile,tile};
        switch_game_tile(c,!g.cover.empty()?g.cover:g.box_front,g.name,r,pos);
        outline(list,r,pos==selected,0.0f);
    }
    list.pop_clip();
    const Game& game=games_[static_cast<std::size_t>(selected)];
    text_shrink(c,game.name,125.0f,baseline(150,55,29),29,kInk,1420.0f);
    text(c,list_position(selected+1,count),1790.0f,baseline(152,50,21),
         21,kSubtle,Align::right);
    if(modal_==Modal::none && confirmation_==Confirmation::none && !message_.empty())
        text_shrink(c,message_,125.0f,baseline(191.0f,48.0f,21.0f),
                    21.0f,message_warning_?gfx::Color::rgb(0xb52733):kSubtle,
                    1530.0f);
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
    case Key::cross:
        // Preserve all game-start checks and remote-file handling.
        press_library(key);
        return;
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
              Line{TR("Filter"),switch_value(services_.filter_labels(),prefs_.filter)},
              Line{TR("Video preset"),switch_value(services_.performance_profile_labels(),prefs_.performance_profile)}};
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
    text_shrink(c,tr("Configure"),695.0f,baseline(811,50,20),
                20,kSubtle,920);
    draw_switch_footer(c,tr("Select a settings category"));
}

void Launcher::draw_switch_files(Canvas& c) {
    draw_switch_header(c,tr("Game files"));
    auto& list=c.list;
    list.rounded_rect({88,160,1744,2},0,kGrey);
    text_shrink(c,browse_dir_,110,baseline(188,48,22),22,kSubtle,1660);
    list.rounded_rect({106,251,1120,675},3,kWhite);
    list.bordered_rect({106,251,1120,675},3,kPaper.with_alpha(0),1.0f,kGrey);
    const int count=static_cast<int>(browse_entries_.size());
    for(int row=files_.first_row();row<=files_.last_row()&&row<count;++row) {
        if(row<0)continue;
        const float top=277.0f+float(row)*88.0f-files_.scroll();
        if(top<260||top>878)continue;
        const Rect cell{128.0f,top,1062.0f,80.0f};
        if(row==files_.selected) {
            list.rounded_rect(cell,3,kFocus);
        } else {
            list.rounded_rect({cell.x,cell.y+79,cell.w,1},0,kGrey);
        }
        const std::string& name=browse_entries_[static_cast<std::size_t>(row)];
        const bool selected=row==files_.selected;
        list.rounded_rect({cell.x+19,cell.y+28,30,23},3,selected?kWhite:kSubtle);
        text_shrink(c,name,cell.x+73,
                    baseline(cell.y,80,25),25,selected?kWhite:kInk,960.0f);
    }
    list.rounded_rect({1270,252,530,540},3,kWhite);
    list.bordered_rect({1270,252,530,540},3,kPaper.with_alpha(0),1,kGrey);
    text_shrink(c,tr("Storage"),1300,baseline(282,56,29),29,kInk,450);
    list.rounded_rect({1300,352,462,1},0,kGrey);
    const std::array<std::string,3> info{
        folder_info_.keys?tr("Keys found"):tr("Keys missing"),
        folder_info_.firmware>0?tr("Firmware ready"):tr("Setup required"),
        folder_info_.games>0?tr("Games found"):tr("No games found")
    };
    for(int i=0;i<3;++i)
        text_shrink(c,info[static_cast<std::size_t>(i)],1305,
            baseline(379+float(i)*105,70,23),23,kSubtle,450);
    draw_switch_footer(c,tr("Browse folders: D-pad / Open: A"));
}

void Launcher::draw_switch_language(Canvas& c) {
    draw_switch_header(c,tr("Language"));
    auto& list=c.list;
    list.rounded_rect({90,153,1740,2},0,kGrey);
    const auto& labels=services_.language_labels();
    const int count=static_cast<int>(labels.size());
    text_shrink(c,tr("Choose the language games use"),116,
                baseline(174,62,23),23,kSubtle,1570);
    const Rect window{122,260,1676,648};
    list.push_clip(window);
    for(int i=language_.first_row();i<=language_.last_row()&&i<count;++i) {
        if(i<0)continue;
        const float top=window.y+float(i)*language_.pitch-language_.scroll();
        const Rect row{146,top,1628,79};
        const bool selected=i==language_.selected;
        if(selected) list.rounded_rect(row,3,kFocus);
        else list.rounded_rect({row.x,row.y+78,row.w,1},0,kGrey);
        text_shrink(c,labels[static_cast<std::size_t>(i)],row.x+32,
                    baseline(row.y,79,26),26,selected?kWhite:kInk,1520);
        if(i==prefs_.language)
            text(c,"OK",row.x+row.w-52,baseline(row.y,79,21),21,
                 selected?kWhite:kInk,Align::center);
    }
    list.pop_clip();
    draw_switch_footer(c,tr("Choose your preferred language"));
}

void Launcher::draw_switch_about(Canvas& c) {
    draw_switch_header(c,tr("About Eden Encore"));
    auto& list=c.list;
    list.rounded_rect({90,163,1740,2},0,kGrey);
    text_shrink(c,tr("Powered by Eden"),142,baseline(208,76,38),38,kInk,1500);
    text_block(c,tr("All credit for the Eden emulator goes to its developers and contributors."),
               146,baseline(318,53,27),27,43,kInk,1530,3);
    list.rounded_rect({146,492,1624,2},0,kGrey);
    text_shrink(c,tr("Eden Encore"),146,baseline(537,66,31),31,kInk,1420);
    text_block(c,tr("Thanks to the whole PS5 homebrew community and to every developer whose drivers, tools and libraries make Eden Encore possible."),
               146,baseline(623,55,24),24,40,kSubtle,1550,3);
    text_shrink(c,version_,146,baseline(815,60,23),23,kSubtle,1450);
    draw_switch_footer(c,tr("Credits and setup"));
}


void Launcher::draw_switch_game(Canvas& c,float opened) {
    auto& d=c.list;
    d.push_opacity(opened);
    const Game* game=library_.selected>=0&&library_.selected<static_cast<int>(games_.size())?
        &games_[static_cast<std::size_t>(library_.selected)]:nullptr;
    advanced_panel(c,tr("Game settings"),game?game->name:std::string{});
    const std::uint64_t id=game?game->title_id:0;
    const bool authored=prefs_.performance_profile>=0&&
        prefs_.performance_profile<kAuthoredVideoProfiles;
    const auto base=VideoPresetForTitle(id,authored?prefs_.performance_profile:1);
    const auto out=[](int v)->const char*{return v==2?"2160p":v==1?"1440p":"1080p";};
    const int baseRenderer=authored?base.renderer:prefs_.renderer;
    const int baseOutput=authored?base.output:prefs_.output;
    const int baseRes=authored?base.resolution:prefs_.resolution;
    const int baseFilter=authored?base.filter:prefs_.filter;
    const int baseFsr=authored?base.fsr_sharpness:prefs_.fsr_sharpness;
    const int baseAa=authored?base.anti_aliasing:prefs_.anti_aliasing;
    const int baseHz=authored?base.refresh:prefs_.refresh;
    static constexpr const char* names[]={
        TR("Console mode"),TR("Renderer"),TR("Video preset"),TR("TV output"),
        TR("Resolution"),TR("Upscaling filter"),TR("FSR sharpness"),
        TR("Anti-aliasing"),TR("Refresh rate"),TR("Button mapping"),TR("Mods"),
        TR("Save data")};
    const auto fallback=[](int local,const std::string& def,
                           const std::string& selected)->std::string{
        return local<0?switch_default(def):selected;
    };
    const auto g=game_settings_;
    const std::array<std::string,12> values={
        game_docked_?tr("Docked"):tr("Handheld"),
        fallback(g.renderer,baseRenderer?"Vulkan":"OpenGL",g.renderer?"Vulkan":"OpenGL"),
        fallback(g.performance_profile,
            switch_value(services_.performance_profile_labels(),prefs_.performance_profile),
            switch_value(services_.performance_profile_labels(),g.performance_profile)),
        fallback(g.output,out(baseOutput),out(g.output)),
        fallback(g.resolution,switch_value(services_.resolution_labels(),baseRes),
            switch_value(services_.resolution_labels(),g.resolution)),
        fallback(g.filter,switch_value(services_.filter_labels(),baseFilter),
            switch_value(services_.filter_labels(),g.filter)),
        fallback(g.fsr_sharpness,std::to_string(baseFsr)+"%",
            std::to_string(g.fsr_sharpness)+"%"),
        fallback(g.anti_aliasing,switch_value(services_.anti_aliasing_labels(),baseAa),
            switch_value(services_.anti_aliasing_labels(),g.anti_aliasing)),
        fallback(g.refresh,hertz(baseHz),hertz(g.refresh)),
        g.own_mapping?
            switch_profile_name(g.controller_layout>=0?g.controller_layout:prefs_.controller_layout,
                                g.mapping):
        g.controller_layout>=0?
            switch_profile_name(g.controller_layout,Eden::BaseMappingForLayout(g.controller_layout)):
            fill(tr("Global ({0})"),{switch_profile_name(prefs_.controller_layout,prefs_.mapping)}),
        mods_.empty()?tr("No mods"):
            game&&!game->mods_enabled?tr("Off"):
            fill(tr("{0} of {1} on"),{
                std::to_string(std::count_if(mods_.begin(),mods_.end(),
                    [](const Mod& m){return m.enabled;})),
                std::to_string(mods_.size())}),
        import_source_==SaveSource::ryujinx?tr("Ryujinx save found"):
            import_source_==SaveSource::folder?tr("Save folder found"):tr("Nothing to import")
    };
    d.push_clip(kAdvancedClip);
    for(int i=game_rows_.first_row();i<=game_rows_.last_row();++i) {
        if(i<0||i>=12)continue;
        const float y=318+float(i)*96-game_rows_.scroll();
        advanced_row(c,y,i==option_,tr(names[i]),values[static_cast<std::size_t>(i)],
                     game_rows_.row_alpha(i,92));
    }
    d.pop_clip();
    if(confirmation_==Confirmation::none)
        advanced_status(c,message_,message_warning_,option_==11?TR("Import"):
                        option_==10?TR("Open"):TR("Change"));
    d.pop_opacity();
}
void Launcher::draw_switch_mods(Canvas& c,float opened) {
    auto& d=c.list;
    d.push_opacity(opened);
    const Game* game=library_.selected>=0&&library_.selected<static_cast<int>(games_.size())?
        &games_[static_cast<std::size_t>(library_.selected)]:nullptr;
    advanced_panel(c,tr("Mods"),game?game->name:std::string{});
    if(mods_.empty())
        text_block(c,fill(tr("No mods for this game yet. Copy each mod's folder to {0}, next to roms/."),
                    {game?services_.mods_folder(game->title_id):std::string{}}),
                   546,baseline(332,72,23),23,40,kInk,828,5);
    else {
        const bool active=!game||game->mods_enabled;
        d.push_clip(kAdvancedClip);
        for(int i=mod_rows_.first_row();i<=mod_rows_.last_row();++i) {
            if(i<0||i>=static_cast<int>(mods_.size()))continue;
            const auto& m=mods_[static_cast<std::size_t>(i)];
            advanced_row(c,318+float(i)*96-mod_rows_.scroll(),
                i==mod_rows_.selected,m.name+" · "+m.kind,
                active&&m.enabled?tr("On"):tr("Off"),mod_rows_.row_alpha(i,92));
        }
        d.pop_clip();
    }
    if(confirmation_==Confirmation::none)
        advanced_status(c,message_,message_warning_,mods_.empty()?
                        TR("Create the folder"):TR("Turn on or off"));
    d.pop_opacity();
}
void Launcher::draw_switch_mapping(Canvas& c,float opened) {
    auto& d=c.list;
    d.push_opacity(opened);
    const Game* game=mapping_for_game_&&library_.selected>=0&&
        library_.selected<static_cast<int>(games_.size())?
        &games_[static_cast<std::size_t>(library_.selected)]:nullptr;
    const ButtonMapping buttons=mapping_for_game_?
        Eden::ResolveSessionButtonMapping(prefs_.controller_layout,prefs_.mapping,
            game_settings_.controller_layout,game_settings_.own_mapping,
            game_settings_.mapping).buttons:prefs_.mapping;
    const int layout=mapping_for_game_&&game_settings_.controller_layout>=0?
        game_settings_.controller_layout:prefs_.controller_layout;
    const std::string profile=switch_profile_name(layout,buttons);
    advanced_panel(c,tr("Button mapping"),game?game->name+" · "+profile:
                   fill(tr("Global controller profile: {0}"),{profile}));
    static constexpr const char* names[]={"A","B","X","Y","L","R","ZL","ZR","+","-",
        TR("Left stick press"),TR("Right stick press")};
    d.push_clip(kAdvancedClip);
    for(int i=mapping_rows_.first_row();i<=mapping_rows_.last_row();++i) {
        if(i<0||i>=kGameButtons)continue;
        const float y=318+float(i)*96-mapping_rows_.scroll();
        const int mapped=buttons[static_cast<std::size_t>(i)];
        const float opacity=mapping_rows_.row_alpha(i,92);
        advanced_row(c,y,i==mapping_rows_.selected,tr(names[i]),
                     switch_pad_label(mapped),opacity);
        // Match the original functional editor: the real physical pad glyph
        // stays visible next to the text, even for triggers and touchpad.
        d.push_opacity(opacity);
        const Pad icon=switch_physical_pad(mapped);
        if(mapped>=4) {
            // The shared physical-pad renderer uses light symbols for shoulder
            // and system keys. A dark neutral keycap is required on the
            // Switch theme's white paper; otherwise L/R are invisible.
            const float width=pad_width(icon,30.0f);
            d.rounded_rect({1030.0f,y+25.0f,std::max(44.0f,width+12.0f),42.0f},
                           9.0f,kInk);
        }
        draw_pad(c,icon,1035.0f,y+46.0f,30.0f);
        d.pop_opacity();
    }
    d.pop_clip();
    if(confirmation_==Confirmation::none)
        advanced_status(c,message_,message_warning_,TR("Change"));
    d.pop_opacity();
}

void Launcher::draw_switch_confirmation(Canvas& c) {
    if(confirmation_==Confirmation::none) return;
    auto& list=c.list;
    list.rounded_rect({0,0,1920,1080},0,kInk.with_alpha(0.52f));
    const Rect panel{512.0f,355.0f,896.0f,345.0f};
    list.shadow({panel.x-9,panel.y-8,panel.w+18,panel.h+20},
                9,32,kBlack.with_alpha(0.18f));
    list.rounded_rect(panel,5,kWhite);
    const char* title=tr("Confirm");
    if(confirmation_==Confirmation::exit_app)
        title=tr("Exit Eden Encore");
    else if(confirmation_==Confirmation::console_mode)
        title=tr("Console mode");
    else if(confirmation_==Confirmation::mapping_reset)
        title=tr("Controls");
    else if(confirmation_==Confirmation::shader_caches)
        title=tr("Diagnostics");
    text_shrink(c,title,563.0f,baseline(382.0f,67.0f,32.0f),
                32.0f,kInk,780.0f);
    list.rounded_rect({563,464,780,2},0,kGrey);
    text_shrink(c,message_,563.0f,baseline(492.0f,75.0f,26.0f),
                26.0f,kInk,780.0f);
    list.rounded_rect({563,607,780,1},0,kGrey);
    list.ring(1038,651,15,2,kSubtle);
    text(c,"B",1038,657,18,kInk,Align::center);
    text_shrink(c,tr("Cancel"),1065,658,21,kInk,112);
    list.ring(1230,651,15,2,kSubtle);
    text(c,"A",1230,657,18,kInk,Align::center);
    text_shrink(c,tr("Confirm"),1258,658,21,kInk,115);
}

void Launcher::draw_switch_dialog(Canvas& c, Modal modal, float opened) {
    auto& list=c.list;
    list.push_opacity(opened);
    const Rect panel{430.0f,113.0f,1060.0f,854.0f};
    list.rounded_rect(panel,3.0f,kWhite);
    list.bordered_rect(panel,3.0f,kWhite,1.5f,kGrey);
    const char *heading=tr("System Settings");
    switch(modal) {
    case Modal::video:heading=tr("Video");break;
    case Modal::audio:heading=tr("Audio");break;
    case Modal::controls:heading=tr("Controls");break;
    case Modal::accessibility:heading=tr("Accessibility");break;
    case Modal::appearance:heading=tr("Appearance");break;
    case Modal::diagnostics:heading=tr("Diagnostics");break;
    default:break;
    }
    text_shrink(c,heading,493.0f,baseline(150.0f,72.0f,36.0f),
                36.0f,kInk,910.0f);
    list.rounded_rect({493,245,932,2},0,kGrey);
    const int total=dialog_rows(modal);
    const int first=modal==Modal::video?std::clamp(option_-2,0,std::max(0,total-5)):0;
    const int last=std::min(total,first+5);
    for(int i=first;i<last;++i) {
        const float y=278.0f+float(i-first)*112.0f;
        const Rect row{495.0f,y,930.0f,101.0f};
        if(i==option_) {
            list.rounded_rect(row,3.0f,gfx::Color::rgb(0xdff8fb));
            list.bordered_rect(row,3.0f,kPaper.with_alpha(0.0f),3.0f,kFocus);
        } else list.rounded_rect({row.x,row.y+100,row.w,1},0,kGrey);
        const char *label="";
        std::string value;
        switch(modal) {
        case Modal::appearance:
            label=i==0?"Encore":"Switch";
            value=(prefs_.ui_theme==i)?tr("Active"):tr("Select");
            break;
        case Modal::accessibility:
            label=i==0?tr("Larger text"):i==1?tr("High contrast"):tr("Reduce motion");
            value=(i==0?prefs_.large_text:i==1?prefs_.high_contrast:prefs_.reduce_motion)?tr("On"):tr("Off");
            break;
        case Modal::audio:
            label=i==0?tr("Game volume"):i==1?tr("Mute"):tr("Menu sounds");
            value=i==0?std::to_string(prefs_.volume)+"%":
                  i==1?(prefs_.mute?tr("On"):tr("Off")):std::to_string(prefs_.menu_volume)+"%";
            break;
        case Modal::video: {
            static constexpr const char* labels[]={
                TR("Renderer"),TR("Video preset"),TR("TV output"),TR("Game resolution"),
                TR("Upscaling filter"),TR("FSR sharpness"),TR("Anti-aliasing"),
                TR("Refresh rate"),TR("FPS overlay")};
            label=tr(labels[i]);
            switch(i) {
            case 0:value=prefs_.renderer?tr("Vulkan (recommended)"):"OpenGL";break;
            case 1:value=switch_value(services_.performance_profile_labels(),prefs_.performance_profile);break;
            case 2:value=prefs_.output==2?"2160p":prefs_.output==1?"1440p":"1080p";break;
            case 3:value=switch_value(services_.resolution_labels(),prefs_.resolution);break;
            case 4:value=switch_value(services_.filter_labels(),prefs_.filter);break;
            case 5:value=std::to_string(prefs_.fsr_sharpness)+"%";break;
            case 6:value=switch_value(services_.anti_aliasing_labels(),prefs_.anti_aliasing);break;
            case 7:value=prefs_.refresh?"120 Hz":"60 Hz";break;
            default:value=prefs_.hud?tr("On"):tr("Off");break;
            }
            break;
        }
        case Modal::controls:
            label=i==0?tr("Button profile"):i==1?tr("Button mapping"):
                  i==2?tr("Vibration"):i==3?tr("Vibration strength"):tr("Stick deadzone");
            value=i==0?(prefs_.controller_layout?"Switch":"PlayStation"):
                i==1?tr("Customize"):i==2?(prefs_.vibration?tr("On"):tr("Off")):
                i==3?std::to_string(prefs_.vibration_strength)+"%":
                     std::to_string(prefs_.stick_deadzone)+"%";
            break;
        case Modal::diagnostics:
            label=i==0?tr("Detailed logging"):tr("Clear cache");
            value=i==0?(prefs_.detailed_logging?tr("On"):tr("Off")):tr("Clear");
            break;
        default:
            label=tr("Select");
            break;
        }
        text_shrink(c,label,row.x+22,baseline(y,101,26),26,kInk,590);
        text_shrink(c,value,row.x+row.w-25,baseline(y,101,24),24,
                    i==option_?kInk:kSubtle,294,Align::right);
    }
    list.rounded_rect({493,888,932,2},0,kGrey);
    text_shrink(c,tr("Change"),1252.0f,baseline(901,51,19),
                19,kInk,180,Align::right);
    text_shrink(c,tr("Back"),1397.0f,baseline(901,51,19),
                19,kInk,100,Align::right);
    list.pop_opacity();
}

void Launcher::press_switch_settings(Key key) {
    if(key==Key::down||key==Key::up||key==Key::left||key==Key::right||
       key==Key::l1||key==Key::r1) {
        // System Settings in the reference stops at the first/last category.
        // Do not change the wrapping behavior of Encore's shared ListView.
        const bool original_wrap=settings_.wrap;
        settings_.wrap=false;
        const bool moved=settings_.move(key==Key::down||key==Key::right||
                                        key==Key::r1?1:-1);
        settings_.wrap=original_wrap;
        if(moved) {
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
