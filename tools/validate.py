"""Static validation for the starunity EX mod.

Substitutes for in-game testing:

  A. structural   every referenced ID exists, every new type is registered,
                  no duplicate sections, cameo files present and well formed
  B. regression   for all 12 countries, the complete set of things a normal
                  player can build must be IDENTICAL before and after the mod
                  -- this is the machine proof of "no effect on normal play"
  C. unlock       with a foreign tech Construction Yard, how much of that
                  faction's tree actually becomes reachable
  D. beacon      the Far Star Support Beacon gates exactly what it should
  E. heroes etc.  hero clones, Boris, Battle Lab, co-op ownership, beacon
  F. the rest     beacon grinder, Death's Hand, Fatal Impact, the auto-repair
                  plugin; and when their snapshots exist, the Touhou/ABC port
                  (Satori, Cirno), Phobos and the QiEr maps

  python tools/validate.py            (paths remembered from build_mod.py)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from moini import Ini                                          # noqa: E402
from motree import Tree, SIDES, ALL12, TYPE_LISTS, split_list  # noqa: E402
import paths                                                   # noqa: E402

# Set in main() from paths.configure(). Validation runs against <work>/output,
# which build_mod.py fills with exactly what it copies into the game folder.
PRISTINE = OUT = CAMEOS = GAME = None

FACTION_YARD = {"GACNST": "SUGACNST", "NACNST": "SUNACNST",
                "YACNST": "SUYACNST", "FACNST": "SUFACNST"}

# Deliberately NOT unlocked. The stock MCVs are [General] BaseUnit, an
# index-based list the AI walks; opening their Owner made AI houses queue and
# abandon foreign Construction Yards (proven in game, then fixed by excluding
# them). The SU tech MCV replaces the capability and is free and unlimited
# from the support power, so nothing is lost.
EXPECTED_LOCKED = {"AMCV", "SMCV", "PCV", "FMCV"}

fails, warns = [], []


def fail(m):
    fails.append(m)
    print("  FAIL " + m)


def warn(m):
    warns.append(m)
    print("  warn " + m)


NEW_PREFIX = "SU"


class Merged:
    """The finished rulesmo.ini. The mod now lives inside this one file, so
    this is just a thin wrapper that also reports which IDs are new."""

    def __init__(self, rules_path, _unused=None):
        self.r = Ini(rules_path)
        self.su = self.r
        self._sec_cache = {}
        stock = Ini(os.path.join(PRISTINE, "rulesmo.ini"))
        self.added = {}
        for L in TYPE_LISTS + ("SuperWeaponTypes", "Projectiles"):
            before = set(stock.list_values(L))
            self.added[L] = [x for x in self.r.list_values(L) if x not in before]

    def section_names(self):
        return set(self.r.section_names())

    def items(self, name):
        if name not in self._sec_cache:
            self._sec_cache[name] = dict(self.r.items(name))
        return self._sec_cache[name]

    def get(self, name, key, default=None):
        return self.items(name).get(key, default)

    def list_values(self, L):
        return self.r.list_values(L)


def build_tree(ini_like):
    t = Tree.__new__(Tree)
    t.ini = ini_like
    from motree import BUILTIN_GENERICS
    t.generics = {k.upper(): split_list(v) for k, v in BUILTIN_GENERICS.items()}
    for k, v in ini_like.items("GenericPrerequisites").items():
        t.generics[k.upper()] = split_list(v)
    t.registered = {L: ini_like.list_values(L) for L in TYPE_LISTS}
    t.list_of = {}
    for L, ts in t.registered.items():
        for x in ts:
            t.list_of.setdefault(x, L)
    t._cache = {}
    return t


def closure(tree, country, seed):
    """Everything a house of `country` starting from `seed` buildings can
    eventually build (buildings first to a fixpoint, then all types)."""
    owned = set(seed)
    changed = True
    while changed:
        changed = False
        for b in tree.registered["BuildingTypes"]:
            if b not in owned and tree.buildable_by(b, country, owned):
                owned.add(b)
                changed = True
    out = set(owned)
    for L in TYPE_LISTS:
        for x in tree.registered[L]:
            if tree.buildable_by(x, country, owned):
                out.add(x)
    return out


def check_mow(mow):
    """Mental Omega World: appended, never replacing. Everything the game's
    own menu and briefing file had is still there, unchanged and in order;
    every new menu entry resolves to a map that is in the new mix."""
    import struct
    import abc_port as ap
    from csftool import Csf
    from mixtool import find
    import build_mod as bm
    bad = []
    bc_old = Ini(bm.game_input(mow.BATTLE), encoding="utf-8-sig")
    bc = Ini(os.path.join(OUT, mow.BATTLE), encoding="utf-8-sig")
    dup = sorted(set(bc.duplicates()) - set(bc_old.duplicates()))
    if dup:
        bad.append(f"菜单有新的重复段 {dup[:3]}")
    moved = [s for s in bc_old.section_names()            # [Battles]: prefix check below
             if s != "Battles" and bc_old.items(s) != bc.items(s)]
    old_b, new_b = list(bc_old.items("Battles").items()), list(bc.items("Battles").items())
    if moved or new_b[:len(old_b)] != old_b:
        bad.append(f"原有菜单被改动 {moved[:3]} / [Battles] 前缀一致 {new_b[:len(old_b)] == old_b}")
    added = new_b[len(old_b):]
    raw = open(os.path.join(OUT, mow.MIX_NAME), "rb").read()
    _, count, _ = struct.unpack_from("<IHI", raw)
    ids = {struct.unpack_from("<I", raw, 10 + i * 12)[0] for i in range(count)}
    mm_old = Ini(bm.game_input(mow.MISSION))
    mm = Ini(os.path.join(OUT, mow.MISSION))
    mm_moved = [s for s in mm_old.section_names() if mm_old.items(s) != mm.items(s)]
    if mm_moved:
        bad.append(f"原有简报被改动 {mm_moved[:3]}")
    missions = [v for k, v in added if not v.upper().startswith("X")]
    for sec in {v for _, v in added}:
        if not bc.has_section(sec):
            bad.append(f"菜单项 {sec} 没有定义")
    for sec in missions:
        scen = bc.get(sec, "Scenario") or ""
        if ap.mix_id(scen) not in ids:
            bad.append(f"{sec} 的地图 {scen} 不在 {mow.MIX_NAME}")
        if not mm.has_section(scen):
            bad.append(f"{scen} 没有简报段")
        bkg = mm.get(scen, "LS800BkgdName")
        if bkg and ap.mix_id(bkg) not in ids and bkg not in find(
                [os.path.join(GAME, f"expandmo{n:02d}.mix") for n in (99, 98, 97, 96, 95, 94)], [bkg]):
            bad.append(f"{scen} 的载入图 {bkg} 找不到")
    for sec, title in mow.ZH_TITLES.items():
        if bc.has_section(sec) and bc.get(sec, "Description") != title:
            bad.append(f"{sec} 标题没换成中文")
    for sec, (k, _old, new) in mow.FIXES.items():
        if bc.get(sec, k) != new:
            bad.append(f"{sec}.{k} 没修正")
    csf_out = os.path.join(OUT, mow.CSF_NAME)
    same = open(csf_out, "rb").read() == open(os.path.join(mow.snap(), mow.CSF_NAME), "rb").read()
    l42 = {n.lower() for n, _ in Csf(csf_out).labels}
    l_base = {n.lower() for n, _ in Csf(os.path.join(paths.ORIGINAL, "ra2md.csf")).labels}
    if not same or l42 & l_base:
        bad.append(f"{mow.CSF_NAME} 同快照 {same} / 与 ra2md.csf 重名 {sorted(l42 & l_base)[:3]}")
    if bad:
        fail(f"Mental Omega World 合并有问题: {bad[:8]}")
    else:
        print(f"  ok   Mental Omega World：{len(missions)} 个任务追加在菜单末尾，原有 {len(old_b)} 个菜单项与 "
              f"{len(bc_old.section_names())} 段逐键未动、简报原有 {len(mm_old.section_names())} 段未动；"
              f"每个任务的地图都在 {mow.MIX_NAME}、都有简报和载入图；{len(l42)} 条字符串与 ra2md.csf 无重名")


def check_local(m, art, t_old, t_new, secs):
    """F. Single-purpose changes, plus the optional parts that were built."""
    import re as _re
    import struct
    from PIL import Image
    import abc_port as ap
    import build_mod as bm
    from csftool import Csf
    print()
    print("=" * 64)
    print("F. 信标回收、死神之手、致命冲击、自动维修；可选：东方/秽浪港移植、Phobos、企鹅包地图")
    print("=" * 64)
    stock = Ini(os.path.join(PRISTINE, "rulesmo.ini"))

    if paths.have_abc():
        # --- the MIX: the engine binary-searches the index with SIGNED ids ------
        raw = open(os.path.join(OUT, ap.MIX_NAME), "rb").read()
        flags, count, _ = struct.unpack_from("<IHI", raw)
        index = [struct.unpack_from("<III", raw, 10 + i * 12) for i in range(count)]
        keys = [ap.signed(i) for i, _, _ in index]
        if flags != 0 or keys != sorted(keys) or len(set(keys)) != len(keys):
            fail(f"{ap.MIX_NAME} 索引不是按有符号 id 严格递增（游戏会找不到文件）")
        else:
            print(f"  ok   {ap.MIX_NAME}：{count} 个文件，索引按有符号 id 严格递增")
        base = 10 + count * 12

        def lookup(name):
            """What the engine does: binary search on signed ids."""
            k, lo, hi = ap.signed(ap.mix_id(name)), 0, count - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                if keys[mid] == k:
                    _, off, size = index[mid]
                    if base + off + size <= len(raw):
                        return raw[base + off:base + off + size]
                    return None
                lo, hi = (mid + 1, hi) if keys[mid] < k else (lo, mid - 1)
            return None

        abp = [s for s in art.section_names() if s.startswith("ABP")]
        seq = {art.get(s, "Sequence") for s in abp} - {None}
        want = [f"{p}{t}.pal" for p in ("abunit", ap.SATORI_PAL) for t in ap.THEATERS]
        want.append("abanim.pal")
        for s in abp:
            if s in seq:
                continue
            if (art.get(s, "Voxel") or "no").lower() == "yes":
                want += [s + ".vxl", s + ".hva"]
            else:
                want.append(s + ".shp")
        abcs = [s for s in secs if s.startswith("ABC_")]
        # voxel units: a turret model per turret, one per charge stage
        for s in abcs:
            img = m.get(s, "Image")
            if not img or (art.get(img, "Voxel") or "no").lower() != "yes":
                continue
            if (m.get(s, "Turret") or "no").lower() in ("yes", "true"):
                for i in range(int(m.get(s, "TurretCount") or 1)):
                    want += [f"{img}tur{i or ''}.vxl", f"{img}tur{i or ''}.hva"]
        snd = Ini(os.path.join(OUT, "soundmo.ini"))
        sound_refs = set()
        for s in abcs + abp:
            for k, v in (m.items(s) if s in abcs else art.items(s)).items():
                if k.lower() in ap.SR:
                    sound_refs |= {x for x in split_list(v) if x.upper().startswith("ABCS_")}
        for s in sound_refs:
            want += [x.lstrip("$!") + ".wav" for x in (snd.get(s, "Sounds") or "").split()]
        lost = [n for n in want if lookup(n) is None]
        if lost:
            fail(f"{len(lost)} 个资源在 {ap.MIX_NAME} 里查不到: {lost[:6]}")
        else:
            print(f"  ok   {len(want)} 个被引用的资源（精灵/模型/色盘/音效）全部可被引擎查到")
        no_def = sorted(s for s in sound_refs if not snd.has_section(s))
        unreg = sorted(sound_refs - set(snd.list_values("SoundList")))
        if no_def or unreg:
            fail(f"音效事件缺定义 {no_def[:4]} / 未注册 {unreg[:4]}")
        else:
            print(f"  ok   {len(sound_refs)} 个音效事件在 soundmo.ini 中已定义并注册")

        R_src = ap.load_source()[0]
        differ = [s for s in ap.SHARED if dict(stock.items(s)) != R_src[s]]
        if differ:
            fail(f"借用原版条目但与源 MOD 不一致: {differ}")
        else:
            print(f"  ok   借用原版 {sorted(ap.SHARED)}：与源 MOD 逐键相同")

        # hit points: STRENGTH_MUL x ABC, unless the user set a value
        hp = {s: (R_src[s[4:]]["Strength"], m.get(s, "Strength")) for s in abcs
              if "UIName" in R_src.get(s[4:], {}) and "Strength" in R_src.get(s[4:], {})}

        def want_hp(s, src_hp):
            fixed = ap.OVERRIDES.get(s[4:], {}).get("Strength")
            return int(fixed) if fixed else int(src_hp) * ap.STRENGTH_MUL
        off = {s: v for s, v in hp.items() if int(v[1]) != want_hp(s, v[0])}
        if off or len(hp) != len(ap.UNITS) + len(ap.VEHICLES) + 1:
            fail(f"血量不对: {off} / 覆盖 {len(hp)} 个单位")
        else:
            print(f"  ok   {len(hp)} 个单位（含上海人形）血量 = 源 MOD × {ap.STRENGTH_MUL}"
                  f"（指定数值的除外：{ {k: v['Strength'] for k, v in ap.OVERRIDES.items()} }）")

        # --- type IDs: Ares refuses anything over 24 characters -----------------
        long_ids = [x for L in TYPE_LISTS + ("Warheads", "Animations", "Particles",
                                             "ParticleSystems")
                    for x in m.list_values(L) if len(x) > 24]
        long_refs = [f"[{s}] {k}={v}" for s in abcs for k, v in m.items(s).items()
                     if ap.ref_domain(k.lower()) and any(len(x) > 24 for x in split_list(v))]
        if long_ids or long_refs:
            fail(f"超过 24 字符的 ID: {(long_ids + long_refs)[:4]}")
        else:
            print(f"  ok   {len(abcs)} 个 ABC_ 段：注册名与引用名均不超过 24 字符")

        # --- who can build what ---------------------------------------------------
        units = [ap.type_id("ABC_", u) for u in ap.UNITS]
        vehicles = [ap.type_id("ABC_", u) for u in ap.VEHICLES]
        missing = [u for u in units + vehicles if u not in secs]
        extra = [s for L in ("InfantryTypes", "VehicleTypes", "AircraftTypes")
                 for s in m.list_values(L)
                 if s.startswith("ABC_") and s not in units + vehicles
                 and m.get(s, "TechLevel") != "-1"]
        if missing or extra:
            fail(f"移植单位缺失 {missing} / 非白名单单位可生产 {extra}")
        else:
            print(f"  ok   只有 {len(units)} 个东方角色 + {len(vehicles)} 辆载具可生产（附属单位 TechLevel=-1）")
        yard = {"NACNST", "NAPOWR", "NAREFN", "SUGACNST"}
        leaked = [u for u in units if t_new.buildable_by(u, "Chinese", yard | {"NAHAND"})]
        leaked += [u for u in vehicles if t_new.buildable_by(u, "Chinese", yard | {"NAWEAP"})]
        if leaked:
            fail(f"没建信标就能造: {leaked}")
        else:
            print("  ok   没建信标 -> 东方角色和载具一个都造不出")
        for rax in ("GAPILE", "NAHAND", "YABRCK", "FABARR"):
            got = [u for u in units if t_new.buildable_by(u, "Chinese", yard | {rax, "SUBEACON"})]
            if len(got) != len(units):
                fail(f"信标 + {rax} 仍造不出: {sorted(set(units) - set(got))}")
                break
        else:
            print("  ok   信标 + 四阵营任一兵营 -> 10 个东方角色全部可造")
        for fac in ("GAWEAP", "NAWEAP", "YAWEAP", "FAWEAP"):
            got = [u for u in vehicles if t_new.buildable_by(u, "Chinese", yard | {fac, "SUBEACON"})]
            if len(got) != len(vehicles):
                fail(f"信标 + {fac} 仍造不出: {sorted(set(vehicles) - set(got))}")
                break
        else:
            print(f"  ok   信标 + 四阵营任一战车工厂 -> {vehicles} 可造")
        for u, want_k in ap.OVERRIDES.items():
            uid = ap.type_id("ABC_", u)
            got_k = {k: m.get(uid, k) for k in want_k}
            if got_k != want_k:
                fail(f"{uid} 指定数值不对: {got_k} 应为 {want_k}")
            else:
                print(f"  ok   {uid}：指定数值 {want_k} 已生效")
        for u in ap.VEHICLES:
            uid = ap.type_id("ABC_", u)
            wpn = [m.get(uid, k) for k in ("Weapon1", "EliteWeapon1")]
            if not all(w and w.startswith("ABC_") and w in secs for w in wpn):
                fail(f"{uid} 武器不对: {wpn}")
            else:
                print(f"  ok   {uid}：武器 {wpn}（秽浪港原版，独立命名）")

        # --- sidebar: PCX cameos, the format MO actually draws ------------------
        bad = []
        for u in units + vehicles:
            img = m.get(u, "Image")
            for k in ("CameoPCX", "AltCameoPCX"):
                f = art.get(img, k)
                p = os.path.join(OUT, f or "-")
                if not f or not os.path.exists(p):
                    bad.append(f"{u}.{k}")
                    continue
                im = Image.open(p)
                if im.format != "PCX" or im.mode != "P" or im.size != (60, 48):
                    bad.append(f"{f} {im.format} {im.mode} {im.size}")
            if art.get(img, "Cameo") or art.get(img, "CameoPalette"):
                bad.append(f"{img} 仍带 SHP Cameo/CameoPalette")
        if bad:
            fail(f"图标问题: {bad[:5]}")
        else:
            print(f"  ok   {len(units + vehicles) * 2} 个图标为 60x48 8位 PCX（CameoPCX/AltCameoPCX）")

        # Cirno: her own copy of the IFV laser; the original stays for Koishi
        mine, base_w = "ABC_" + ap.CIRNO_LASER, "ABC_" + ap.CIRNO_LASER_FROM
        src_l = R_src[ap.CIRNO_LASER_FROM]
        sec_w = {m.get("ABC_CIRNO", k) for k in ("Secondary", "EliteSecondary")}
        ok_l = (sec_w == {mine}
                and abs(float(m.get(mine, "Range")) - float(src_l["Range"]) * ap.CIRNO_LASER_RANGE_MUL) < 1e-6
                and int(m.get(mine, "Damage")) == int(src_l["Damage"]) * ap.CIRNO_LASER_DAMAGE_MUL
                and m.get(mine, "Projectile") == "ABC_InvisibleAll"
                and m.get(base_w, "Range") == src_l["Range"]
                and m.get(base_w, "Damage") == src_l["Damage"]
                and m.get("ABC_KOISHI", "ElitePrimary") == base_w)
        if not ok_l:
            fail(f"琪露诺对空激光不对: {sec_w} {m.items(mine)}")
        else:
            print(f"  ok   琪露诺副武器 {mine}：射程 {src_l['Range']}→{m.get(mine, 'Range')}，"
                  f"伤害 {src_l['Damage']}→{m.get(mine, 'Damage')}，可对空；"
                  f"恋的精英武器仍用未改的 {base_w}")

        # Satori: Koishi's sprite through an inverted palette, medic kit
        sid = ap.type_id("ABC_", ap.SATORI)
        simg = m.get(sid, "Image")
        kimg = m.get(ap.type_id("ABC_", "KOISHI"), "Image")
        pal_ok = all(lookup(f"{ap.SATORI_PAL}{t}.pal") ==
                     ap._invert_pal(lookup(f"abunit{t}.pal")) for t in ap.THEATERS)
        shp_ok = lookup(simg.lower() + ".shp") == lookup(kimg.lower() + ".shp")
        if not (pal_ok and shp_ok and art.get(simg, "Palette") == ap.SATORI_PAL):
            fail(f"古明地觉的反相美术不对: 色盘 {pal_ok} 精灵 {shp_ok} Palette={art.get(simg, 'Palette')}")
        else:
            print(f"  ok   古明地觉：精灵与恋逐字节相同，6 个地形色盘均为反相（{ap.SATORI_PAL}*.pal）")
        bad_w = []
        for key, (new, old) in ap.SATORI_WEAPONS.items():
            mine_w, orig = dict(m.items(new)), dict(stock.items(old))
            want_rof = str(max(1, round(int(orig["ROF"]) / ap.SATORI_ROF_DIV)))
            if m.get(sid, key) != new or mine_w.pop("ROF") != want_rof or \
                    mine_w.pop("Range") != ap.SATORI_RANGE or \
                    {k: v for k, v in orig.items() if k not in ("ROF", "Range")} != mine_w:
                bad_w.append(key)
            if dict(m.items(old)) != orig:
                bad_w.append(f"原版 {old} 被改动")
        if bad_w:
            fail(f"古明地觉的治疗武器不对: {bad_w}")
        else:
            print(f"  ok   古明地觉：武器 = 军医 Heal/Heal2 的复制，射击间隔 "
                  f"{stock.get('Heal', 'ROF')}→{m.get('ABC_SatoriHeal', 'ROF')}，射程 "
                  f"{stock.get('Heal', 'Range')}→{m.get('ABC_SatoriHeal', 'Range')}"
                  "（其余逐键相同，原版未动）")
        wrong = {k: m.get(sid, k) for k, v in ap.SATORI_KEYS.items() if m.get(sid, k) != v}
        wrong.update({k: m.get(sid, k) for k in ap.SATORI_NO_KEYS if m.get(sid, k) is not None})
        if wrong:
            fail(f"古明地觉的设定键不对: {wrong}")
        else:
            print(f"  ok   古明地觉：造价 {m.get(sid, 'Cost')}，默认区域警戒，警戒范围 "
                  f"{m.get(sid, 'GuardRange')}，治疗射程 {m.get('ABC_SatoriHeal', 'Range')}")
    else:
        print("  skip 东方/秽浪港移植：没有 abc_source 快照，这次没生成")

    # the beacon doubles as the Grinder; its SpecialAnim is the model played once
    g_want = {k: stock.get(bm.GRINDER_DONOR, k) for k in bm.GRINDER_KEYS}
    g_have = {k: m.get("SUBEACON", k) for k in bm.GRINDER_KEYS}
    bart = art.items(m.get("SUBEACON", "Image"))
    act, spc = bart.get("ActiveAnim"), bart.get("SpecialAnim")
    same = {k: v for k, v in art.items(act).items() if k != "LoopCount"} == \
           {k: v for k, v in art.items(spc or "-").items() if k != "LoopCount"}
    anim_ok = (spc == bm.BEACON_SPECIAL and same and art.get(spc, "LoopCount") == "1"
               and spc in m.list_values("Animations"))
    gate = {"Owner", "RequiredHouses", "ForbiddenHouses", "FactoryOwners", "Prerequisite"}
    g_moved = ({k: v for k, v in stock.items(bm.GRINDER_DONOR).items() if k not in gate} !=
               {k: v for k, v in m.items(bm.GRINDER_DONOR).items() if k not in gate})
    if g_have != g_want or not anim_ok or g_moved:
        fail(f"信标的回收功能不对: {g_have} 应为 {g_want} / 回收动画 {spc} / 原版被改 {g_moved}")
    else:
        print(f"  ok   信标兼任部队回收厂：{g_have} 与原版 {bm.GRINDER_DONOR} 一致；"
              f"回收动画 {spc} = 模型动画 {act} 只播一遍（看不出动画，模型不再消失）；"
              "原版回收厂未改动")

    # Death's Hand: only its two weapons, only those two keys, no unit uses them
    dh_bad = []
    for w in bm.DEATHS_HAND_WEAPONS:
        before = dict(stock.items(w))
        want_w = dict(before, Damage=bm.DEATHS_HAND_DAMAGE,
                      ROF=str(int(before["ROF"]) * bm.DEATHS_HAND_ROF_MUL))
        if dict(m.items(w)) != want_w:
            dh_bad.append(w)
    users = [(s, k) for s in m.section_names() if s != "WeaponTypes"
             for k, v in m.items(s).items()
             if any(_re.search(rf"(^|,)\s*{w}\s*(,|$)", v) for w in bm.DEATHS_HAND_WEAPONS)]
    if dh_bad or users:
        fail(f"死神之手武器不对: {dh_bad} / 规则里有单位在用 {users[:4]}")
    else:
        print(f"  ok   死神之手：{'/'.join(bm.DEATHS_HAND_WEAPONS)} 伤害 "
              f"{stock.get(bm.DEATHS_HAND_WEAPONS[0], 'Damage')}→{bm.DEATHS_HAND_DAMAGE}，"
              f"开火间隔 {stock.get(bm.DEATHS_HAND_WEAPONS[0], 'ROF')}→"
              f"{m.get(bm.DEATHS_HAND_WEAPONS[0], 'ROF')}；规则里没有单位用它们（只有苏军最终关地图）")

    # Fatal Impact: exactly the timer lines and Volkov's Size differ
    a_map = open(os.path.join(PRISTINE, bm.FATAL_MAP), "rb").read().split(b"\n")
    b_map = open(os.path.join(OUT, bm.FATAL_MAP), "rb").read().split(b"\n")
    changed = [1 for x, y in zip(a_map, b_map) if x != y]
    want_n = len(bm.FATAL_TIMER_TRIGGERS) + 1
    fm = Ini(os.path.join(OUT, bm.FATAL_MAP))
    ok_t = all(f",27,0,{bm.FATAL_TIMER_TO}," in fm.get("Actions", t) for t in bm.FATAL_TIMER_TRIGGERS)
    if len(a_map) != len(b_map) or len(changed) != want_n or not ok_t \
            or fm.get("VOLKOV", "Size") != bm.FATAL_VOLKOV_SIZE[1]:
        fail(f"致命冲击地图改动不对: 改了 {len(changed)} 行（应为 {want_n}）计时 {ok_t} "
             f"体积 {fm.get('VOLKOV', 'Size')}")
    else:
        print(f"  ok   致命冲击：只改 {len(changed)} 行 —— 主任务计时 3 处 "
              f"{bm.FATAL_TIMER_FROM}→{bm.FATAL_TIMER_TO} 秒（4 小时），"
              f"变身前沃尔科夫体积 {bm.FATAL_VOLKOV_SIZE[0]}→{bm.FATAL_VOLKOV_SIZE[1]}")

    # our auto-repair plugin: hooks must not overlap Ares', and the third-party
    # MO_ExperienceEnhancements plugin it replaced must be gone
    import pefile as _pe

    def _hooks(path):
        pe = _pe.PE(path)
        b0 = pe.OPTIONAL_HEADER.ImageBase
        out = []
        for s in pe.sections:
            if s.Name.startswith(b".syhks"):
                d = s.get_data()
                for i in range(0, len(d) - 15, 16):
                    a, sz, np_, _ = struct.unpack_from("<IIII", d, i)
                    if a:
                        out.append((a, sz, pe.get_data(np_ - b0, 64).split(b"\0")[0].decode()))
        return out
    ours = _hooks(os.path.join(OUT, "MOAutoRepair.dll"))
    ares = _hooks(os.path.join(GAME, "Ares.dll"))
    clash = [(hex(a), n, hex(b), bn) for a, s1, n in ours for b, s2, bn in ares
             if a < b + s2 and b < a + s1]
    leftovers = [f for f in ("MOExperience.dll", "MOExperience.ini")
                 if os.path.exists(os.path.join(GAME, f))]
    if clash or not ours or leftovers:
        fail(f"自动维修插件有问题: 与 Ares 重叠 {clash} / 钩子 {ours} / 旧插件残留 {leftovers}")
    else:
        print(f"  ok   自动维修插件 MOAutoRepair.dll：{len(ours)} 个钩子 "
              f"{[(hex(a), n) for a, _, n in ours]}，与 Ares 的 {len(ares)} 个零重叠；旧插件已移除")

    if paths.have_phobos():
        # Phobos: UI switches exactly as intended, nothing else in uimd.ini moved,
        # the DLL is the snapshot, and its hooks/patches live with Ares and ours
        ui = Ini(os.path.join(OUT, "uimd.ini"))
        ui_bad = {f"{s}.{k}": ui.get(s, k) for s, pairs in bm.UIMD_KEYS for k, v in pairs
                  if ui.get(s, k) != v}
        ui_stock = Ini(os.path.join(PRISTINE, "uimd.ini"))
        touched = {s for s, _ in bm.UIMD_KEYS}
        ui_moved = [s for s in ui_stock.section_names()
                    if s not in touched and dict(ui_stock.items(s)) != dict(ui.items(s))]
        ph_out = os.path.join(OUT, "Phobos.dll")
        same_dll = os.path.isfile(ph_out) and \
            open(ph_out, "rb").read() == open(os.path.join(paths.PHOBOS_DIR, "Phobos.dll"), "rb").read()
        phobos = _hooks(ph_out) if os.path.isfile(ph_out) else []
        ph_ares = [(hex(a), n) for a, s1, n in phobos for b, s2, bn in ares
                   if a != b and a < b + s2 and b < a + s1]
        ph_ours = [(hex(a), n) for a, s1, n in phobos for b, s2, bn in ours
                   if a < b + s2 and b < a + s1 and (a, s1) != (b, s2)]
        pe = _pe.PE(ph_out)
        patches = []
        for s in pe.sections:
            if s.Name.startswith(b".patch"):
                d = s.get_data()
                for i in range(0, len(d) - 11, 12):
                    o, z, _p = struct.unpack_from("<III", d, i)
                    if 0x401000 <= o < 0x898000 and 0 < z < 0x1000:
                        patches.append((o, z))
        ph_patch = [(hex(o), z) for o, z in patches for b, s2, _n in ours if o < b + s2 and b < o + z]
        # Phobos refuses MO's Syringe: Syringe.exe must be the SyringeEx snapshot,
        # and the client must launch it with SyringeEx's command line
        syr = open(os.path.join(OUT, "Syringe.exe"), "rb").read()
        syringe_ex = syr == open(paths.SYRINGE_EX, "rb").read()
        cd_out = Ini(os.path.join(OUT, bm.CLIENT_DEFS))
        cd_stock = Ini(os.path.join(paths.ORIGINAL, bm.CLIENT_DEFS))
        cd_bad = {k: cd_out.get("Settings", k) for k, v in bm.CLIENT_LAUNCH if cd_out.get("Settings", k) != v}
        launch_keys = {k for k, _ in bm.CLIENT_LAUNCH}
        cd_moved = [s for s in cd_stock.section_names()
                    if {k: v for k, v in cd_stock.items(s).items() if k not in launch_keys} !=
                    {k: v for k, v in cd_out.items(s).items() if k not in launch_keys}]
        args = (cd_out.get("Settings", "ExtraCommandLineParams") or "")
        flags_ok = all(f in args for f in ("-SPAWN", "-SPEEDCONTROL", "-AFFINITY:"))
        ui_bad.update({f"rules[{s}].{k}": m.get(s, k) for s, k, v in bm.RULES_UI_KEYS if m.get(s, k) != v})
        if ui_bad or ui_moved or not same_dll or ph_ares or ph_ours or ph_patch \
                or not syringe_ex or cd_bad or cd_moved or not flags_ok:
            fail(f"Phobos 有问题: 开关 {ui_bad} / uimd 其它段被改 {ui_moved} / DLL 同快照 {same_dll} / "
                 f"与 Ares 部分重叠 {ph_ares[:3]} / 与本插件冲突 {ph_ours} / 补丁碰本插件 {ph_patch} / "
                 f"SyringeEx {syringe_ex} / 启动参数 {cd_bad} / 客户端配置其它处被改 {cd_moved} / "
                 f"-SPAWN -SPEEDCONTROL -AFFINITY 齐全 {flags_ok}")
        else:
            print(f"  ok   Phobos：uimd.ini {sum(len(p) for _, p in bm.UIMD_KEYS)} 个界面开关就位、其它段未动；"
                  f"{len(phobos)} 个钩子与 Ares 无部分重叠，与自动维修插件只有同址同长度（可串联）；"
                  f"{len(patches)} 个补丁不碰本插件")
            print(f"  ok   加载器为 SyringeEx 0.7.2.0；客户端启动参数 {args}；客户端配置只改了启动三项")
    else:
        print("  skip Phobos：没有快照，这次没生成")

    if paths.have_qier_maps():
        # QiEr maps: registered once each, entry == snapshot, files byte-identical,
        # every [#include] shipped, modes/forced options resolvable, 东风谷-改 absent
        import json
        import qier_maps as qm
        mi = Ini(os.path.join(OUT, "INI", "MentalOmegaMaps.ini"), encoding="utf-8-sig")
        reg = [v.lower() for v in mi.list_values("MultiMaps")]
        secs_l = {s.lower() for s in mi.section_names()}
        snap = json.load(open(os.path.join(paths.QIER_SNAP, "entries.json"), encoding="utf-8"))
        qm_bad = []
        for mp in qm.MAPS:
            name = qm.entry_name(mp)
            if reg.count(name.lower()) != 1:
                qm_bad.append(f"{mp} 登记 {reg.count(name.lower())} 次")
            if mi.items(name) != {k: v.split(";")[0].strip() for k, v in snap[mp]}:
                qm_bad.append(f"{mp} 条目与快照不同")
            d = dict(snap[mp])
            for gm in d.get("GameModes", "").split(","):
                if gm.strip() and gm.strip().lower() not in secs_l:
                    qm_bad.append(f"{mp} 模式 {gm} 无定义")
            if d.get("ForcedOptions") and d["ForcedOptions"].lower() not in secs_l:
                qm_bad.append(f"{mp} ForcedOptions {d['ForcedOptions']} 无定义")
            for ext in (".map", ".png"):
                out_f = os.path.join(OUT, "MapsMO", qm.FOLDER, mp + ext)
                if not os.path.isfile(out_f) or open(out_f, "rb").read() != \
                        open(os.path.join(paths.QIER_SNAP, mp + ext), "rb").read():
                    qm_bad.append(f"{mp}{ext} 缺失或与快照不同")
            for inc in qm.includes(os.path.join(paths.QIER_SNAP, mp + ".map")):
                if inc not in qm.EXTRA_FILES or not os.path.isfile(os.path.join(OUT, inc)):
                    qm_bad.append(f"{mp} 引用 {inc} 未部署")
        for f in qm.EXTRA_FILES:
            if open(os.path.join(OUT, f), "rb").read() != open(os.path.join(paths.QIER_SNAP, f), "rb").read():
                qm_bad.append(f"{f} 与快照不同")
        leaked = [x for x in qm.EXCLUDED if any(x.lower() in r for r in reg) or
                  os.path.exists(os.path.join(OUT, "MapsMO", qm.FOLDER, x + ".map"))]
        if qm_bad or leaked:
            fail(f"企鹅包地图有问题: {qm_bad[:8]} / 不该有的图 {leaked}")
        else:
            print(f"  ok   企鹅包地图：{len(qm.MAPS)} 张各登记一次、条目同快照、模式与强制选项可解析、"
                  f"文件逐字节一致、[#include] {', '.join(qm.EXTRA_FILES)} 已部署；东风谷-改 未带入")
    else:
        print("  skip 企鹅包地图：没有快照，这次没生成")

    import mow
    if mow.available():
        check_mow(mow)
    else:
        print("  skip Mental Omega World：没有快照，这次没生成")

    if paths.have_abc():
        csf = Csf(os.path.join(OUT, "ra2md.csf"))
        unnamed =[u for u in units + vehicles if not csf.get(m.get(u, "UIName") or "")]
        if unnamed:
            fail(f"缺中文名: {unnamed}")
        else:
            print(f"  ok   {len(units + vehicles)} 个移植单位均有中文名")
    else:
        print("  skip 东方单位中文名：没有生成")



def main():
    global PRISTINE, OUT, CAMEOS, GAME
    ap = argparse.ArgumentParser(description="Noob Edition static validation")
    paths.add_args(ap)
    paths.configure(ap.parse_args())
    PRISTINE, OUT, CAMEOS, GAME = paths.PRISTINE, paths.OUTPUT, paths.CAMEOS, paths.GAME
    print("=" * 64)
    print("A. 结构检查")
    print("=" * 64)
    m = Merged(os.path.join(OUT, "rulesmo.ini"))
    art = Ini(os.path.join(OUT, "artmo.ini"))
    secs = m.section_names()

    # every new type is registered exactly once
    reg_all = []
    for L in TYPE_LISTS:
        reg_all += m.list_values(L)
    dupes = {x for x in reg_all if reg_all.count(x) > 1}
    if dupes:
        fail(f"注册列表里有重复条目: {sorted(dupes)[:10]}")
    if os.path.exists(os.path.join(OUT, "starunity.ini")):
        fail("output 里仍残留 starunity.ini（应已并入 rulesmo.ini）")
    else:
        print(f"  ok   注册类型 {len(reg_all)} 个，无重复")

    for L in TYPE_LISTS + ("SuperWeaponTypes", "Projectiles"):
        for x in m.added.get(L, []):
            if x not in secs:
                fail(f"{L} 注册了 {x} 但没有对应段定义")
    print(f"  ok   新增注册 {sum(len(v) for v in m.added.values())} 条，段定义齐全")

    # every referenced ID exists
    REFS = ("Prerequisite", "DeploysInto", "UndeploysInto", "Deliver.Types",
            "Primary", "Secondary", "ElitePrimary", "EliteSecondary",
            "Projectile", "Warhead", "SidebarPCX", "CameoPCX")
    art_secs = set(art.section_names())
    su_sections = sorted({x for v in m.added.values() for x in v})
    generics = {k.upper() for k in m.items("GenericPrerequisites")}
    from motree import BUILTIN_GENERICS
    generics |= set(BUILTIN_GENERICS)
    missing = []
    for s in su_sections:
        for k, v in m.items(s).items():
            if k not in REFS:
                continue
            if k in ("SidebarPCX", "CameoPCX"):
                if not os.path.exists(os.path.join(OUT, v)):
                    fail(f"[{s}] {k}={v} 文件不存在")
                continue
            for tok in split_list(v):
                if tok in ("none", "None", ""):
                    continue
                if tok in secs or tok.upper() in generics:
                    continue
                missing.append(f"[{s}] {k} -> {tok}")
    if missing:
        for x in missing[:20]:
            fail("引用了不存在的 ID: " + x)
    else:
        print(f"  ok   {len(su_sections)} 个新段的引用全部可解析")

    # Image must name an artmo entry, or match a stock type whose own art the
    # engine will find by name.
    # An Image= value names a graphics entry: either an artmo section, a rules
    # section, or a raw art-file stem MO itself already points at (building art
    # lives in nested theater mixes we do not unpack).
    stock_images = {art.get(a, "Image") for a in art_secs if art.get(a, "Image")}
    bad_img = [f"[{s2}] Image={m.get(s2, 'Image')}" for s2 in su_sections
               if m.get(s2, "Image")
               and m.get(s2, "Image").lower() != "none"
               and m.get(s2, "Image") not in art_secs
               and m.get(s2, "Image") not in secs
               and m.get(s2, "Image") not in stock_images]
    if bad_img:
        for x in bad_img[:10]:
            fail("Image 指向的美术条目不存在: " + x)
    else:
        print(f"  ok   新段的 Image 全部指向已有美术条目")

    sw_reg = set(m.list_values("SuperWeaponTypes"))
    for s2 in su_sections:
        for k in ("SuperWeapon", "SuperWeapon2", "SuperWeapons"):
            for tok in split_list(m.get(s2, k) or ""):
                if tok not in sw_reg:
                    fail(f"[{s2}] {k} 引用了未注册的超武 {tok}")
    print("  ok   新建筑挂载的超武都已注册")

    # a clone that converts/deploys into another cloned type must point at the
    # clone, not at the stock partner the player has no tech for
    clone_names = {x for x in su_sections if x.startswith(NEW_PREFIX)}
    stock_of = {x[len(NEW_PREFIX):] for x in clone_names}
    misdirected = []
    for c in sorted(clone_names):
        for k in ("Convert.Deploy", "Convert.Water", "Convert.Land",
                  "UndeploysInto", "DeploysInto", "UpgradesTo", "Spawns"):
            val = m.get(c, k)
            if not val:
                continue
            for tok in split_list(val):
                if tok in stock_of:
                    misdirected.append(f"[{c}] {k}={tok}")
    if misdirected:
        for x in misdirected[:10]:
            fail("克隆体指回了原版伙伴: " + x)
    else:
        print(f"  ok   {len(clone_names)} 个克隆体的转换/展开引用都指向克隆体")

    # generic prerequisites resolve
    for g, v in m.items("GenericPrerequisites").items():
        for tok in split_list(v):
            if tok not in secs:
                fail(f"[GenericPrerequisites] {g} 引用了不存在的 {tok}")

    # cameos
    try:
        from PIL import Image
        for f in sorted(os.listdir(CAMEOS)):
            im = Image.open(os.path.join(CAMEOS, f))
            if im.size != (60, 48) or im.mode != "P":
                fail(f"图标 {f} 规格错误: {im.size} {im.mode}")
        print(f"  ok   {len(os.listdir(CAMEOS))} 个图标均为 60x48 8位带调色板 PCX")
    except ImportError:
        warn("PIL 不可用，跳过图标检查")

    # co-op unlock: BOTH the mode sections and every per-map entry. The client
    # reads the per-map one -- with only the mode sections cleared it still
    # refuses with "selected map can only be used on CnCNet or LAN".
    maps = Ini(os.path.join(OUT, "INI", "MentalOmegaMaps.ini"), encoding="utf-8-sig")
    for mode in ("Co-Op Easy", "Co-Op Medium", "Co-Op Hard"):
        for k in ("HumanPlayersOnly", "MultiplayerOnly"):
            if maps.get(mode, k):
                fail(f"[{mode}] 仍然有 {k}")
    print("  ok   3 个合作模式的联机限制已解除")
    coop_secs = [x for x in maps.section_names()
                 if x.lower().startswith(r"mapsmo\cooperative" + "\\")]
    stuck = [x for x in coop_secs if maps.get(x, "MultiplayerOnly")]
    if stuck:
        fail(f"{len(stuck)} 个地图条目仍带 MultiplayerOnly: {stuck[:3]}")
    else:
        print(f"  ok   {len(coop_secs)} 个合作地图条目已去掉 MultiplayerOnly")

    # co-op map files must not carry the engine-level lobby-only flag either
    coop = os.path.join(OUT, "MapsMO", "Cooperative")
    if os.path.isdir(coop):
        bad = [f for f in sorted(os.listdir(coop)) if f.lower().endswith(".map")
               and Ini(os.path.join(coop, f)).get("Basic", "MultiplayerOnly")]
        if bad:
            fail(f"{len(bad)} 张合作地图仍带 MultiplayerOnly: {bad[:5]}")
        else:
            n = len([f for f in os.listdir(coop) if f.lower().endswith(".map")])
            print(f"  ok   {n} 张合作地图已去掉 MultiplayerOnly")

    # ==================================================================
    print()
    print("=" * 64)
    print("B. 回归证明：普通遭遇战必须逐条目一致")
    print("=" * 64)
    t_old = Tree(Ini(os.path.join(PRISTINE, "rulesmo.ini")))
    t_new = build_tree(m)
    total_diff = 0
    for cy, (en, cn, countries) in SIDES.items():
        for country in sorted(countries):
            a = closure(t_old, country, {cy})
            b = closure(t_new, country, {cy})
            gained, lost = b - a, a - b
            if gained or lost:
                total_diff += len(gained) + len(lost)
                fail(f"{cn}/{country}: 多出 {len(gained)} {sorted(gained)[:8]} "
                     f"少了 {len(lost)} {sorted(lost)[:8]}")
            else:
                print(f"  ok   {cn}/{country:<14} 可建造 {len(a):>3} 项，改前改后完全一致")
    if total_diff == 0:
        print("  >>> 12 个国家全部一致 —— 普通遭遇战零影响，已证明")

    # ==================================================================
    print()
    print("=" * 64)
    print("C. 外籍科技解锁覆盖率")
    print("=" * 64)
    clones = {x[2:]: x for L in TYPE_LISTS for x in m.added.get(L, [])
              if x.startswith("SU")}
    everyone = {}
    for k, (_e, _c2, cs) in SIDES.items():
        everyone[k] = set().union(*[closure(t_old, c, {k}) for c in cs])
    for cy, (en, cn, _c) in SIDES.items():
        others = set().union(*[everyone[k] for k in SIDES if k != cy])
        exclusive = everyone[cy] - others          # stock faction-only content
        for ocy, (oen, ocn, ocountries) in SIDES.items():
            if ocy == cy:
                continue
            country = sorted(ocountries)[0]
            base = closure(t_new, country, {ocy})
            gained = closure(t_new, country, {ocy, FACTION_YARD[cy]}) - base
            got = {x for x in exclusive
                   if x in gained or clones.get(x) in gained}
            miss = sorted(exclusive - got)
            # An entry with no Prerequisite never appears in the sidebar: it is
            # spawned by a weapon (carrier planes, SW missiles, drones), so it
            # is not something the player could "build" in the first place.
            real_miss = [x for x in miss if t_old.ini.get(x, "Prerequisite")
                         and x not in EXPECTED_LOCKED]
            buildable = [x for x in exclusive if t_old.ini.get(x, "Prerequisite")
                         and x not in EXPECTED_LOCKED]
            got_b = [x for x in buildable if x in got]
            pct = 100.0 * len(got_b) / max(1, len(buildable))
            print(f"  {ocn:<6}(用{country:<12}) + {cn:<6}科技基地车 -> "
                  f"可建造项 {len(got_b):>3}/{len(buildable):>3} = {pct:5.1f}%"
                  f"   (另有 {len(miss) - len(real_miss)} 个召唤物不进侧边栏)")
            if real_miss:
                fail(f"{ocn}+{cn}: 有 {len(real_miss)} 个真实可建造项未解锁: {real_miss[:8]}")

    # ==================================================================
    print()
    print("=" * 64)
    print("D. 远星支援信标：解锁门是否真的成立")
    print("=" * 64)
    BEACON = "SUBEACON"
    TEN = ["SUQUICK", "SUAHVYBOT2", "SUGRUMBLE", "SUMAMM", "SUIDRAG",
           "SUTRACTOR", "SUWORMQ", "SUPHNT", "SUSEITAAD", "SURAMW"]
    country = "Chinese"                       # a Soviet player, arbitrary pick
    # closure() would happily build the beacon itself, so the gate has to be
    # probed directly against an explicit set of owned buildings.
    base = {"NACNST", "NAWEAP", "NAPOWR", "NAREFN", "SUGACNST", "GAWEAP"}
    without = [u for u in TEN if t_new.buildable_by(u, country, base)]
    withb = [u for u in TEN if t_new.buildable_by(u, country, base | {BEACON})]
    no_yard = closure(t_new, country, {"NACNST"})
    with_yard = closure(t_new, country, {"NACNST", "SUGACNST"})
    with_beacon = set(withb)
    leaked = without
    if BEACON not in with_yard:
        fail(f"有科技建造场却造不出 {BEACON}")
    else:
        print(f"  ok   有任一科技建造场 -> 可造 {BEACON}")
    if BEACON in no_yard:
        fail(f"没有科技建造场也能造 {BEACON}")
    else:
        print(f"  ok   没有科技建造场 -> 造不出 {BEACON}")
    if leaked:
        fail(f"没建信标就能造: {leaked}")
    else:
        print(f"  ok   没建信标 -> 10 个单位一个都造不出")
    missing = [u for u in TEN if u not in with_beacon]
    if missing:
        fail(f"建了信标仍造不出: {missing}")
    else:
        print(f"  ok   建了信标 -> 10 个单位全部可造")
    # the stock stolen-tech units must not have moved
    stock_ten = ["QUICK", "AHVYBOT2", "GRUMBLE", "MAMM", "IDRAG",
                 "TRACTOR", "WORMQ", "PHNT", "SEITAAD", "RAMW"]
    moved = [u for u in stock_ten
             if dict(t_old.ini.items(u)) != dict(m.items(u))]
    if moved:
        fail(f"原版偷取科技单位被改动了: {moved}")
    else:
        print("  ok   原版那 10 个偷取科技单位逐键未改动")

    # ==================================================================
    print()
    print("=" * 64)
    print("E. 英雄步兵 / 作战实验室 / 合作任务归属")
    print("=" * 64)
    HERO_ARMORS = {"tany", "krukov", "moral", "f_hero", "yunru", "under",
                   "libra", "librc", "rahn", "sib_fin", "sib_ali", "eureka",
                   "sieg", "c_hero", "c_hero2"}
    import build_mod as bm
    EGGS = bm.HERO_SKIP - {"AIMORA"}         # easter eggs + Libra's clone, left out
    stock_heroes = [x for x in t_old.registered["InfantryTypes"]
                    if (t_old.ini.get(x, "Armor") or "").strip() in HERO_ARMORS
                    and x != "AIMORA" and x not in EGGS]
    hero_clones = [NEW_PREFIX + x for x in stock_heroes]
    bid = NEW_PREFIX + bm.BORIS
    if bid in secs:                          # rebuilt from the challenge map
        hero_clones.append(bid)
    absent = [h for h in hero_clones if h not in secs]
    if absent:
        fail(f"英雄克隆缺失: {absent[:6]}")
    else:
        print(f"  ok   {len(hero_clones)} 个英雄步兵克隆全部存在")
    eggs = [NEW_PREFIX + x for x in EGGS if NEW_PREFIX + x in secs]
    if eggs:
        fail(f"彩蛋单位仍被克隆: {eggs}")
    else:
        print(f"  ok   彩蛋单位 {sorted(EGGS)} 未克隆（原版不受影响）")
    no_heal = [h for h in hero_clones if m.get(h, "SelfHealing") != "yes"]
    slow = [f"{h}={m.get(h, 'BuildTimeMultiplier')}" for h in hero_clones
            if float(m.get(h, "BuildTimeMultiplier") or 1) > 2]
    if no_heal or slow:
        fail(f"英雄克隆 无自愈 {no_heal[:4]} / 造兵时间倍率 >2 {slow[:4]}")
    else:
        print("  ok   英雄克隆全部 SelfHealing=yes，造兵时间倍率均不超过 2")
    if bid in secs and GAME:
        # every key comes from MO's own map definition except those set on
        # purpose; his art, cameo and weapons must exist in the stock data
        src_b = dict(Ini(os.path.join(PRISTINE, bm.BORIS_MAP)).items(bm.BORIS))
        on_purpose = set(bm.BORIS_KEYS) | {"Owner", "Prerequisite", "TechLevel",
                                           "AIBuildThis", "SelfHealing", "Image"}
        drift = {k for k in src_b if k not in on_purpose and src_b[k] != m.get(bid, k)}
        img = m.get(bid, "Image")
        lost = [x for x in (m.get(bid, "Primary"), m.get(bid, "ElitePrimary"),
                            m.get(bid, "Secondary")) if not m.r.has_section(x)]
        if drift or lost or not art.get(img, "CameoPCX"):
            fail(f"鲍里斯不对: 偏离地图定义 {drift} / 武器缺失 {lost} / 美术 {img}")
        else:
            print(f"  ok   {bid}：按挑战地图的 MO 官方定义复原，美术/图标/武器沿用原版")

    # heroes whose stock art has no cameo get their own art entry, a sprite
    # copied under that name, and a drawn cameo; the stock art stays as it is
    stock_art = Ini(os.path.join(PRISTINE, "artmo.ini"))
    for u, (shp, _b, _a, label, _f) in bm.HERO_CAMEOS.items():
        own = NEW_PREFIX + u
        img = m.get(own, "Image")
        files = [art.get(img, k) for k in ("CameoPCX", "AltCameoPCX")]
        pcx_ok = all(f and os.path.exists(os.path.join(OUT, f)) for f in files)
        shp_ok = os.path.exists(os.path.join(OUT, img.lower() + ".shp")) and \
            open(os.path.join(OUT, img.lower() + ".shp"), "rb").read() == \
            open(os.path.join(PRISTINE, shp), "rb").read()
        art_same = {k: v for k, v in art.items(img).items() if "Cameo" not in k} == \
            dict(stock_art.items(u))
        untouched = dict(stock_art.items(u)) == dict(art.items(u))
        if img != own or not (pcx_ok and shp_ok and art_same and untouched):
            fail(f"{own} 图标/美术不对: Image={img} 图标 {pcx_ok} 精灵 {shp_ok} "
                 f"美术同原版 {art_same} 原版未动 {untouched}")
        else:
            print(f"  ok   {own}（{label}）：自有美术段 + 复制精灵 {img.lower()}.shp + "
                  f"图标 {files}；原版 [{u}] 美术未动")

    # FRIENDLY_SAFE clones: the whole shot chain is a private, friendly-safe copy
    for u, keys in bm.FRIENDLY_SAFE.items():
        cid = NEW_PREFIX + u
        chain, todo = [], [m.get(cid, k) for k in keys]
        while todo:
            w = todo.pop()
            if w in chain:
                continue
            chain.append(w)
            wh, pj = m.get(w, "Warhead"), m.get(w, "Projectile")
            chain += [x for x in (wh, pj) if x]
            for k in ("AirburstWeapon", "ShrapnelWeapon"):
                if pj and m.get(pj, k):
                    todo.append(m.get(pj, k))
        chain = list(dict.fromkeys(chain))
        whs = [x for x in chain if m.get(x, "Verses")]
        bad = ([x for x in chain if not x.startswith(NEW_PREFIX)] +
               [x for x in whs if m.get(x, "AffectsAllies") != "no"] +
               ([] if bm.FRIENDLY_SAFE_KEEP_PIERCE else
                [x for x in chain if m.get(x, "AmbientDamage")]))
        if bad:
            fail(f"{cid} 不伤友军复制链有问题: {bad}")
        else:
            print(f"  ok   {cid}：射击链 {len(chain)} 段全部是私有复制，{len(whs)} 个弹头 "
                  "AffectsAllies=no")
    base = {"NACNST", "NAHAND", "NAPOWR", "NAREFN", "SUGACNST", "GAPILE"}
    leaked = [h for h in hero_clones if t_new.buildable_by(h, "Chinese", base)]
    got = [h for h in hero_clones
           if t_new.buildable_by(h, "Chinese", base | {"SUBEACON"})]
    if leaked:
        fail(f"没建信标就能造的英雄: {leaked[:6]}")
    else:
        print("  ok   没建信标 -> 英雄一个都造不出")
    if len(got) != len(hero_clones):
        fail(f"建了信标仍造不出: {sorted(set(hero_clones) - set(got))[:6]}")
    else:
        print(f"  ok   信标 + 任意兵营 -> {len(got)} 个英雄全部可造")
    # The gate keys are touched by the group-1 Owner pass, whose harmlessness
    # part B already proves. Everything else about a stock hero must be
    # untouched -- no stats, no weapons, no art.
    GATE = {"Owner", "RequiredHouses", "ForbiddenHouses", "FactoryOwners",
            "Prerequisite"}
    def body(d):
        return {k: v for k, v in d.items() if k not in GATE}
    moved = [x for x in stock_heroes
             if body(dict(t_old.ini.items(x))) != body(dict(m.items(x)))]
    if moved:
        fail(f"原版英雄的非门键被改动了: {moved[:6]}")
    else:
        gated = [x for x in stock_heroes
                 if dict(t_old.ini.items(x)) != dict(m.items(x))]
        print(f"  ok   原版 {len(stock_heroes)} 个英雄：数值/武器/美术逐键未改动"
              f"（其中 {len(gated)} 个的门键随第1组一起开放，已由 B 段证明无影响）")

    LAB, LABC = "GATECH", NEW_PREFIX + "GATECH"
    if LABC not in secs:
        fail(f"{LABC} 不存在")
    elif t_new.buildable_by(LABC, "Chinese", {"SUGACNST"}):
        print(f"  ok   只有盟军科技建造场 -> 可造 {LABC}（盟军作战实验室）")
    else:
        fail(f"有 SUGACNST 却造不出 {LABC}")
    if t_new.buildable_by(LABC, "Chinese", {"NACNST", "NAHAND"}):
        fail(f"没有盟军科技建造场也能造 {LABC}")
    else:
        print(f"  ok   没有盟军科技建造场 -> 造不出 {LABC}")
    if dict(t_old.ini.items(LAB)) != dict(m.items(LAB)):
        diff = {k for k in set(dict(t_old.ini.items(LAB))) | set(dict(m.items(LAB)))
                if t_old.ini.get(LAB, k) != m.get(LAB, k)}
        print(f"  note 原版 {LAB} 变动的键: {sorted(diff)}（Owner 开放属预期）")
    else:
        print(f"  ok   原版 {LAB} 逐键未改动")

    import re as _re
    coop_dir = os.path.join(OUT, "MapsMO", "Cooperative")
    left, checked = [], 0
    for fn in sorted(os.listdir(coop_dir)):
        if not fn.lower().endswith(".map"):
            continue
        checked += 1
        mp = Ini(os.path.join(coop_dir, fn))
        for sect in ("Events", "Actions"):
            for start, end in mp.sections.get(sect, []):
                for i in range(start + 1, end):
                    if _re.search(r"(^|,)4476(,|$)", mp.lines[i].split("=", 1)[-1]):
                        left.append(f"{fn}:{sect}")
    # slot 2 is also encoded as a House= string on TeamTypes/ScriptTypes;
    # missing it left reinforcement teams (e.g. "Reznov Arrives") orphaned
    enemy_before = {"C": 1099, "D": 763, "E": 73}
    enemy_now = {k: 0 for k in enemy_before}
    for fn in sorted(os.listdir(coop_dir)):
        if not fn.lower().endswith(".map"):
            continue
        for ln in open(os.path.join(coop_dir, fn), encoding="latin-1"):
            t = ln.strip()
            if not t.startswith("House="):
                continue
            if "<Player @ B>" in t:
                left.append(f"{fn}:House")
            for k in enemy_now:
                if f"<Player @ {k}>" in t:
                    enemy_now[k] += 1
    if enemy_now != enemy_before:
        fail(f"敌方位置的小队归属被误改: {enemy_now} 应为 {enemy_before}")
    else:
        print(f"  ok   敌方位置 C/D/E 的小队归属未被触碰 {enemy_now}")
    if left:
        fail(f"合作地图仍残留 2 号位引用: {sorted(set(left))[:5]}")
    else:
        print(f"  ok   {checked} 张合作地图已无 2 号位引用（数字 4476 与 House=<Player @ B> 两套编码）")

    # the ally slot must be optional: with slot 2's half handed to slot 1, an
    # ally house would own nothing and the engine defeats it on frame 1.
    bad_min = [fn for fn in sorted(os.listdir(coop_dir))
               if fn.lower().endswith(".map")
               and Ini(os.path.join(coop_dir, fn)).get("Basic", "MinPlayer") != "1"]
    if bad_min:
        fail(f"{len(bad_min)} 张地图的 [Basic] MinPlayer 仍不是 1: {bad_min[:4]}")
    else:
        print(f"  ok   {checked} 张合作地图 [Basic] MinPlayer=1（可单人开局）")
    mm = Ini(os.path.join(OUT, "INI", "MentalOmegaMaps.ini"), encoding="utf-8-sig")
    bad_cl = [x for x in mm.section_names()
              if x.lower().startswith("mapsmo" + chr(92) + "cooperative" + chr(92))
              and mm.get(x, "MinPlayers") != "1"]
    if bad_cl:
        fail(f"{len(bad_cl)} 个客户端条目的 MinPlayers 仍不是 1")
    else:
        print("  ok   36 个客户端条目 MinPlayers=1（大厅允许一个人开始）")

    # the beacon doubles as the seven tech buildings, and has its own cameo
    need = {}
    for donor in bm.TECH_DONORS:
        for k in bm.TECH_EFFECT:
            v = t_old.ini.get(donor, k)
            if v:
                need[k] = max(need.get(k, 0.0), float(v))
    have = {k: float(m.get("SUBEACON", k) or 0) for k in bm.TECH_EFFECT}
    moved = [d for d in bm.TECH_DONORS
             if dict(t_old.ini.items(d)) != dict(m.items(d))]
    if have != need or moved:
        fail(f"信标的科技建筑效果不对: 应为 {need} 实为 {have} / 原版被改 {moved}")
    else:
        print(f"  ok   信标兼任 7 个科技建筑：{len(need)} 个效果键与原版逐项一致，"
              "原版科技建筑未改动")
    bimg = m.get("SUBEACON", "Image")
    pcx = art.get(bimg, "CameoPCX")
    if not pcx or not os.path.isfile(os.path.join(CAMEOS, pcx)) \
            or art.get(bimg, "Image") != "GABSTA":
        fail(f"信标图标/模型设置不对: Image={bimg} CameoPCX={pcx}")
    else:
        print(f"  ok   信标：自有美术段 [{bimg}]（模型沿用 GABSTA）+ 图标 {pcx}")

    check_local(m, art, t_old, t_new, secs)

    print()
    print("=" * 64)
    print(f"结果：{len(fails)} 个错误，{len(warns)} 个警告")
    print("=" * 64)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
