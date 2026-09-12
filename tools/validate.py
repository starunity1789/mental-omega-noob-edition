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
PRISTINE = OUT = CAMEOS = None


def configure(args):
    global PRISTINE, OUT, CAMEOS
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
        print("  ok   6 个图标均为 60x48 8位带调色板 PCX")
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

    print()
    print("=" * 64)
    print(f"结果：{len(fails)} 个错误，{len(warns)} 个警告")
    print("=" * 64)
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Athos Edition static validation")
    ap.add_argument("--game", default=None,
                    help="unused, accepted so both scripts take the same flags")
    ap.add_argument("--work", default=None,
                    help="scratch directory used by build_mod.py")
    configure(ap.parse_args())
    sys.exit(main())
