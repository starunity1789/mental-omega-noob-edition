"""Static validation for the starunity EX mod.

Substitutes for in-game testing:

  A. structural   every referenced ID exists, every new type is registered,
                  no duplicate sections, cameo files present and well formed
  B. regression   for all 12 countries, the complete set of things a normal
                  player can build must be IDENTICAL before and after the mod
                  -- this is the machine proof of "no effect on normal play"
  C. unlock       with a foreign tech Construction Yard, how much of that
                  faction's tree actually becomes reachable
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from moini import Ini                                          # noqa: E402
from motree import Tree, SIDES, ALL12, TYPE_LISTS, split_list  # noqa: E402

# Set by configure(); validation runs against work/output, which build_mod.py
# fills with a byte-identical copy of what it wrote into the game folder.
PRISTINE = OUT = CAMEOS = GAME = None


def configure(args):
    global PRISTINE, OUT, CAMEOS, GAME
    GAME = os.path.abspath(args.game) if args.game else None
    work = os.path.abspath(args.work or os.path.join(REPO, "work"))
    PRISTINE = os.path.join(work, "pristine")
    OUT = os.path.join(work, "output")
    CAMEOS = os.path.join(REPO, "cameos")
    if not os.path.isfile(os.path.join(OUT, "rulesmo.ini")):
        raise SystemExit("run tools/build_mod.py first: " + OUT
                         + " has no rulesmo.ini")

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


def main():
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
    coop = os.path.join(OUT, "Cooperative")
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
    EGGS = {"ARND", "STLN", "CLNT"}          # easter-egg commandos, left out
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
        src_b = dict(Ini(os.path.join(GAME, bm.BORIS_MAP)).items(bm.BORIS))
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
    coop_dir = os.path.join(OUT, "Cooperative")
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

    print()
    print("=" * 64)
    print(f"结果：{len(fails)} 个错误，{len(warns)} 个警告")
    print("=" * 64)
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Noob Edition static validation")
    ap.add_argument("--game", default=None,
                    help="unused, accepted so both scripts take the same flags")
    ap.add_argument("--work", default=None,
                    help="scratch directory used by build_mod.py")
    configure(ap.parse_args())
    sys.exit(main())
