"""Mental Omega World (MahBoiDeveloper/MentalOmegaWorld, CC BY-NC 4.0): fan-made
single-player missions, merged into whatever campaign menu the game already has.

The pack's own install replaces INI/BattleClient.ini (the campaign menu) and
missionmo.ini (briefings and loading screens) with files that list only its
own missions - MO's campaigns, and any other mission pack, drop out of the
menu. Here nothing is replaced: its menu groups and missions are appended to
the existing BattleClient.ini, its briefing sections to the existing
missionmo.ini. Maps and loading screens go into their own expandmo42.mix,
the Chinese strings into stringtable42.csf (as the pack names them). Its
language switcher (Resources/OptionsWindow.ini) and mapselmo.ini (the old
single-player map screen, not used by the client) are left out.

  build_mod.py --mow "<MentalOmegaWorld checkout>"   one-off snapshot into
                                                     <work>/third_party/mow/
  build_mod.py                                       merges it on every run

Menu titles left in English by the pack are given Chinese ones (ZH_TITLES).
Fixed on the way in (both are bugs in the pack):
  - [FAEARTH] is defined twice in its menu file; kept once.
  - [FASPARK02] (Allied "Spark On The Mars") points Scenario= at the Foehn
    map FFSPARK02.MAP; it now loads its own FASPARK02.MAP (Euro Alliance,
    Abrams - checked in the map).
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths                                             # noqa: E402
from moini import Ini                                    # noqa: E402

MIX_NAME = "expandmo42.mix"
CSF_NAME = "stringtable42.csf"
BATTLE = os.path.join("INI", "BattleClient.ini")
MISSION = "missionmo.ini"
KEY_PREFIX = "MOW"                 # [Battles] keys, so they never collide
SNAP_FILES = {                     # snapshot name -> path under the checkout
    "BattleClient.ini": os.path.join("Source", "BattleClientCHN.ini"),
    "missionmo.ini": os.path.join("Source", "missionmo.ini"),
    CSF_NAME: os.path.join("Source", "stringtable42CHN.csf"),
    "creditsMOW.txt": os.path.join("Source", "creditsMOW.txt"),
    "Credits.md": "Credits.md",
    "LICENSE.md": "LICENSE.md",
}
MIX_DIR = os.path.join("Source", "MIX", "expandmo42")
FIXES = {"FASPARK02": ("Scenario", "FFSPARK02.MAP", "FASPARK02.MAP")}
# Menu titles the pack's Chinese file leaves in English, and its group
# headings in the style of MO's own menu. Missions that replay an official MO
# level from another side reuse MO's official Chinese name for it. Only the
# menu line changes; the in-game text of these missions is MO's own Chinese.
ZH_TITLES = {
    "XFANMSNDESCRIPTION": "—— 玩家自制任务（Mental Omega World）——",
    "XFAPRA2": "—— 反转红警2 ——",
    "XSCORPIONS": "—— 天蝎组织编年史 ——",
    "XVETNAMWAR": "—— 越南战争 ——",
    "XUNSORTED": "—— 未分类 ——",
    "FSFA02": "反转红警2 苏军02：鹰击长空",
    "FFSPARK01": "焚风特殊行动：太空火花",
    "FFSPARK02": "焚风特殊行动：火星火花",
    "FASPARK02": "盟军特殊行动：火星火花",
    "FAEARTH": "盟军特殊行动：地出",
    "FFJUGGER": "焚风特殊行动：主宰",
    "FFRED": "焚风特殊行动：力量嗜欲",
    "FEDRAGON": "厄普西隆特殊行动：巨龙风暴",
    "FEECLIPSE": "厄普西隆特殊行动：星蚀",
}


def snap():
    return os.path.join(paths.THIRD, "mow")


def available():
    return os.path.isfile(os.path.join(snap(), "BattleClient.ini"))


def extract(checkout):
    if os.path.isdir(os.path.join(checkout, "Source")) is False and \
            os.path.basename(os.path.normpath(checkout)).lower() == "source":
        checkout = os.path.dirname(os.path.normpath(checkout))
    dst = snap()
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.join(dst, "mix"))
    for name, rel in SNAP_FILES.items():
        shutil.copy2(os.path.join(checkout, rel), os.path.join(dst, name))
    src = os.path.join(checkout, MIX_DIR)
    for f in sorted(os.listdir(src)):
        shutil.copy2(os.path.join(src, f), os.path.join(dst, "mix", f))
    print(f"快照完成：Mental Omega World {len(os.listdir(os.path.join(dst, 'mix')))} 个"
          f"地图/载入图文件 + 菜单 + 简报 + 中文字符串 -> {dst}")


def mow_menu():
    """The pack's menu as (labels, battles, missions): label/mission sections
    in file order with duplicates dropped, and the [Battles] value list."""
    bc = Ini(os.path.join(snap(), "BattleClient.ini"), encoding="utf-8-sig")
    battles = list(bc.items("Battles").items())
    seen, sections = set(), []
    for s in bc.section_names():
        if s == "Battles" or s.lower() in seen:
            continue
        seen.add(s.lower())
        d = dict(bc.items(s))
        if s in ZH_TITLES:
            d["Description"] = ZH_TITLES[s]
        if s in FIXES:
            k, old, new = FIXES[s]
            assert d.get(k) == old, (s, d.get(k))
            d[k] = new
        sections.append((s, d))
    used = {v for _, v in battles}
    sections = [(s, d) for s, d in sections if s in used]     # drops disabled ones
    return battles, sections


def unmerge(rel, ini, before):
    """Take our additions back out of a game file that something else changed
    after we merged into it (another mission pack's installer), so that only
    that other change becomes the new original. `before` is the old snapshot:
    whatever it already had is never removed."""
    keep = {s.lower() for s in before.section_names()}
    if rel == BATTLE:
        ini.delete_lines_matching("Battles", rf"^{KEY_PREFIX}\w*\s*=")
        names = [s for s, _ in mow_menu()[1]]
    else:
        names = Ini(os.path.join(snap(), "missionmo.ini")).section_names()
    for s in names:
        if s.lower() not in keep:
            ini.delete_section(s)
    while len(ini.lines) > 1 and ini.lines[-1].strip() == "" and ini.lines[-2].strip() == "":
        ini.lines.pop()
    ini._reindex()


def build(battle_ini, mission_ini):
    """Append the pack to the game's own campaign menu and briefing file
    (both moini Ini objects, edited in place). Returns {game rel path: bytes}."""
    import abc_port
    battles, sections = mow_menu()
    have = {s.lower() for s in battle_ini.section_names()}
    clash = [s for s, _ in sections if s.lower() in have and s.upper() != "XNULL"]
    assert not clash, f"BattleClient.ini already has {clash}"
    keys = set(battle_ini.items("Battles"))
    new_keys = [f"{KEY_PREFIX}{k}" for k, _ in battles]
    assert not keys & set(new_keys), "Battles keys taken"
    # one blank line in the menu between the existing campaigns and the pack
    entries = [(f"{KEY_PREFIX}_GAP", "XNULL")] + list(zip(new_keys, [v for _, v in battles]))
    start, end = battle_ini.sections["Battles"][-1]
    ins = end
    while ins > start + 1 and battle_ini.lines[ins - 1].strip() == "":
        ins -= 1
    battle_ini.lines[ins:ins] = [f"{k}={v}" for k, v in entries]
    battle_ini._reindex()
    for s, d in sections:
        if s.lower() not in have:
            battle_ini.append_section(s, list(d.items()))
    mm = Ini(os.path.join(snap(), "missionmo.ini"))
    have_m = {s.lower() for s in mission_ini.section_names()}
    added = 0
    for s in mm.section_names():
        assert s.lower() not in have_m, f"missionmo.ini already has [{s}]"
        mission_ini.append_section(s, list(mm.items(s).items()))
        added += 1
    mix_dir = os.path.join(snap(), "mix")
    files = {f: open(os.path.join(mix_dir, f), "rb").read() for f in sorted(os.listdir(mix_dir))}
    n_maps = sum(f.lower().endswith(".map") for f in files)
    out = {MIX_NAME: abc_port.write_mix(files),
           CSF_NAME: open(os.path.join(snap(), CSF_NAME), "rb").read()}
    n_missions = sum(1 for s, _ in sections if not s.upper().startswith("X"))
    return out, dict(missions=n_missions, maps=n_maps, briefings=added,
                     mix_files=len(files),
                     groups=sum(1 for s, _ in sections if s in ZH_TITLES and s.startswith("X")))


if __name__ == "__main__":
    print(__doc__)
