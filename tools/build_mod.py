"""Noob Edition patch generator for Mental Omega 3.3.6.

Ships no Mental Omega content. It reads the pristine rules straight out of
your own installation's expandmo99.mix, applies the Noob Edition changes and
writes the result back into the game folder.

  python tools/build_mod.py --game "D:/Games/Mental Omega"
  python tools/build_mod.py --game "..." --dry       build to work/output only
  python tools/build_mod.py --game "..." --restore   undo everything
  python tools/validate.py   --game "..."            prove nothing else moved

The first run snapshots every file it is about to touch into work/backup, so
--restore puts the installation back exactly as it was.

What it produces
  rulesmo.ini            pristine + surgical edits, then the whole new-content
                         block appended between STARUNITY EX BEGIN/END markers
  artmo.ini              pristine + art sections for the new types
  ra2md.csf              stock strings + names for the new content
  INI/MentalOmegaMaps.ini  co-op modes unlocked for skirmish
  *.pcx                  six support-power cameos
  (backup only) starunity_block.ini — readable copy of the appended block

Why one file instead of an [#include]: [GenericPrerequisites] is evaluated
before an included file's "+=" registrations exist, so every ANY*=...,SU*
entry failed to parse. Verified in game: 64 warnings with the include, 0 with
everything inside rulesmo.ini.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from moini import Ini                                    # noqa: E402
from motree import Tree, SIDES, ALL12_STR, split_list    # noqa: E402
from csftool import Csf                                  # noqa: E402
from mixtool import extract                              # noqa: E402

# Set by configure(); every path is derived from --game / --work.
GAME = PRISTINE = BACKUP = OUTPUT = CAMEOS = None

# Files the patch overwrites, relative to the game folder. Snapshotted on the
# first run so --restore is exact.
TOUCHED = ["ra2md.csf", os.path.join("INI", "MentalOmegaMaps.ini")]
MARKER = "STARUNITY EX BEGIN"        # sentinel written into rulesmo.ini


def configure(args):
    global GAME, PRISTINE, BACKUP, OUTPUT, CAMEOS
    GAME = os.path.abspath(args.game)
    work = os.path.abspath(args.work or os.path.join(REPO, "work"))
    PRISTINE = os.path.join(work, "pristine")
    BACKUP = os.path.join(work, "backup")
    OUTPUT = os.path.join(work, "output")
    CAMEOS = os.path.join(REPO, "cameos")
    for d in (PRISTINE, BACKUP, OUTPUT):
        os.makedirs(d, exist_ok=True)
    if not os.path.isfile(os.path.join(GAME, "expandmo99.mix")):
        raise SystemExit("not a Mental Omega 3.3.6 folder (no expandmo99.mix): "
                         + GAME)


def already_patched():
    p = os.path.join(GAME, "rulesmo.ini")
    if not os.path.isfile(p):
        return False
    with open(p, "r", encoding="latin-1", errors="ignore") as fh:
        return MARKER in fh.read()


def prepare():
    """Pull pristine data out of the mixes and snapshot what we will modify."""
    need = [n for n in ("rulesmo.ini", "artmo.ini")
            if not os.path.isfile(os.path.join(PRISTINE, n))]
    if need:
        mixes = [os.path.join(GAME, "expandmo%d.mix" % n)
                 for n in (99, 98, 97, 96, 95, 94)]
        done, missing = extract(mixes, need, PRISTINE)
        for n, m, sz in done:
            say("[prepare] extracted %s (%s bytes) from %s"
                % (n, format(sz, ","), os.path.basename(m)))
        if missing:
            raise SystemExit("could not find %s inside the game's mix files"
                             % missing)

    snap = os.path.join(BACKUP, "original")
    coop_bak = os.path.join(BACKUP, "Cooperative")
    first_run = not os.path.isdir(snap)
    if first_run and already_patched():
        raise SystemExit(
            "rulesmo.ini is already patched but work/backup is missing, so the "
            "originals cannot be recovered. Delete the game's rulesmo.ini and "
            "artmo.ini (the game falls back to the copies inside "
            "expandmo99.mix), restore ra2md.csf, INI/MentalOmegaMaps.ini and "
            "MapsMO/Cooperative from a clean install, then run again.")
    os.makedirs(snap, exist_ok=True)
    for rel in TOUCHED:
        dst_f = os.path.join(snap, os.path.basename(rel))
        if not os.path.isfile(dst_f):
            shutil.copy2(os.path.join(GAME, rel), dst_f)
    os.makedirs(coop_bak, exist_ok=True)
    game_coop = os.path.join(GAME, "MapsMO", "Cooperative")
    if os.path.isdir(game_coop) and not os.listdir(coop_bak):
        for f in sorted(os.listdir(game_coop)):
            if f.lower().endswith(".map"):
                shutil.copy2(os.path.join(game_coop, f),
                             os.path.join(coop_bak, f))
    if first_run:
        say("[prepare] snapshotted the originals -> " + snap)


def restore():
    """Put the installation back the way it was."""
    snap = os.path.join(BACKUP, "original")
    if not os.path.isdir(snap):
        raise SystemExit("nothing to restore: work/backup/original is missing")
    for rel in TOUCHED:
        src_f = os.path.join(snap, os.path.basename(rel))
        if os.path.isfile(src_f):
            shutil.copy2(src_f, os.path.join(GAME, rel))
            say("[restore] " + rel)
    coop_bak = os.path.join(BACKUP, "Cooperative")
    game_coop = os.path.join(GAME, "MapsMO", "Cooperative")
    if os.path.isdir(coop_bak) and os.path.isdir(game_coop):
        n = 0
        for f in sorted(os.listdir(coop_bak)):
            shutil.copy2(os.path.join(coop_bak, f), os.path.join(game_coop, f))
            n += 1
        say("[restore] %d co-op maps" % n)
    for f in ("rulesmo.ini", "artmo.ini"):
        p = os.path.join(GAME, f)
        if os.path.isfile(p):
            os.remove(p)
            say("[restore] removed %s (the game falls back to expandmo99.mix)" % f)
    for f in sorted(os.listdir(CAMEOS)):
        p = os.path.join(GAME, f)
        if os.path.isfile(p):
            os.remove(p)
    say("[restore] done - the installation is back to stock")

P = "SU"                       # ID prefix — verified collision-free in MO 3.3.6

# side key -> (stock MCV, new MCV, new ConYard, cameo file, Chinese side name)
FACTION = {
    "GACNST": ("AMCV", "SUAMCV", "SUGACNST", "sucmcva.pcx", "盟军", "allied"),
    "NACNST": ("SMCV", "SUSMCV", "SUNACNST", "sucmcvs.pcx", "苏军", "soviet"),
    "YACNST": ("PCV",  "SUPCV",  "SUYACNST", "sucmcvy.pcx", "厄普西隆", "epsilon"),
    "FACNST": ("FMCV", "SUFMCV", "SUFACNST", "sucmcvf.pcx", "焚风", "foehn"),
}

# id, delivered type, cameo, ASCII internal name, Chinese name (CSF only)
SUPERWEAPONS = [
    ("SUSWSHIN", "SHINBOT", "sucshin.pcx", "Deliver Decimator",   "传送：长剑毁灭装甲"),
    ("SUSWHYBR", "GAHYBR",  "suchybr.pcx", "Deliver Hybrid Tower", "传送：混合塔"),
    ("SUSWMCVA", "SUAMCV",  "sucmcva.pcx", "Deliver Allied TechMCV",  "传送：盟军科技基地车"),
    ("SUSWMCVS", "SUSMCV",  "sucmcvs.pcx", "Deliver Soviet TechMCV",  "传送：苏军科技基地车"),
    ("SUSWMCVY", "SUPCV",   "sucmcvy.pcx", "Deliver Epsilon TechMCV", "传送：厄普西隆科技基地车"),
    ("SUSWMCVF", "SUFMCV",  "sucmcvf.pcx", "Deliver Foehn TechMCV",   "传送：焚风科技基地车"),
]

# Copied verbatim from the user's working v1 superweapon, so behaviour matches
# a configuration already proven in game.  Only the per-power keys differ.
SW_TEMPLATE = [
    ("IsPowered", "no"), ("Money.Amount", "0"), ("RechargeTime", "0.1"),
    ("Type", "UnitDelivery"), ("Action", "Custom"), ("ShowTimer", "no"),
    ("DisableableFromShell", "no"), ("Range", "1.5"), ("LineMultiplier", "0"),
    ("Cursor", "WarpIn"), ("NoCursor", "NoWarpIn"),
    ("EVA.Ready", "EVA_ReinforcementsReady"),
    ("SW.Animation", "WARPMIN"), ("SW.AnimationHeight", "5"),
    ("SW.Sound", "ChronoMinerTeleport"), ("SW.FireIntoShroud", "yes"),
    ("SW.AITargeting", "none"), ("SW.Group", "17"), ("SW.Deferment", "5"),
    ("SW.CreateRadarEvent", "no"),
    ("SW.Inhibitors", "CACEAS,FAINHI,FAINHIB,RACC,COON,FAJAMM"),
    ("FlashSidebarTabFrames", "0"),
    ("SW.AllowAI", "no"), ("SW.AllowPlayer", "yes"), ("SW.AlwaysGranted", "yes"),
]

# ---------------------------------------------------------------------------
# Far Star Support Beacon (远星支援信标)
#
# A new building every tech Construction Yard can put up. It carries one
# support power and it is the sole key to ten of Mental Omega's stolen-tech
# units, which normally need a spy infiltration to unlock.
# ---------------------------------------------------------------------------
BEACON = "SUBEACON"
BEACON_DONOR = "GABSTA"                 # Blackout Research Station, a map prop
BEACON_YARD_GENERIC = "ANYSUYARD"       # satisfied by any of the four SU yards

BEACON_SW = "SUSWKNGT"
BEACON_SW_DONOR = "PaladinAidSpecial"
BEACON_SW_DELIVERS = "SREF,SREF,ABRM,ABRM,BLZZ,BLZZ,PANTHER,PANTHER,SDRN"
BEACON_SW_COST = "-8500"
BEACON_SW_RECHARGE = "0.25"             # 15 seconds

# Stolen-tech units the beacon unlocks. Cloned rather than unlocked in place:
# the real gate lives in INI/Game Options/Stolen Tech.ini, which overrides
# rulesmo.ini at launch, and editing it would change ordinary skirmish play.
BEACON_UNLOCKS = ["QUICK", "AHVYBOT2", "GRUMBLE", "MAMM", "IDRAG",
                  "TRACTOR", "WORMQ", "PHNT", "SEITAAD", "RAMW"]
# Transform partners of the above; cloned so a deployed clone does not hand
# back a stock unit the player has no tech for.
BEACON_PARTNERS = {"AHVYBOT2B": "VehicleTypes", "NAGRUM": "BuildingTypes"}

# ---------------------------------------------------------------------------
# Allied Battle Lab (盟军作战实验室 = stock GATECH)
#
# Some campaign/co-op maps lock the Allied high-tech branch through their own
# INI overrides, which target the stock ID. A clone gated purely on the Allied
# tech Construction Yard is out of their reach.
# ---------------------------------------------------------------------------
LAB_CLONES = {"GATECH": "GACNST"}        # cloned building -> gating SU yard

# ---------------------------------------------------------------------------
# Hero infantry (英雄级步兵)
#
# Identified from MO's own [ArmorTypes] "Heroes Infantry Group" block rather
# than by name, so the list cannot drift. Unlocked at any faction's barracks
# once the Far Star Support Beacon stands.
# ---------------------------------------------------------------------------
HERO_ARMORS = {"tany", "krukov", "moral", "f_hero", "yunru", "under", "libra",
               "librc", "rahn", "sib_fin", "sib_ali", "eureka", "sieg",
               "c_hero", "c_hero2"}
# AIMORA is the AI-only duplicate of MORALES (its prerequisite carries AILOCK).
HERO_SKIP = {"AIMORA"}

# ---------------------------------------------------------------------------
# Co-op: hand the ally's half of the mission to player 1
#
# Every co-op map scripts two player slots. 4475/4476 are the map-format codes
# for "player at position 1/2"; rewriting 4476 -> 4475 across the trigger data
# makes slot 2's units, reinforcements and objective triggers all belong to
# slot 1, so one person can run missions that need both halves played actively.
# ---------------------------------------------------------------------------
COOP_P2 = "4476"
COOP_P1 = "4475"

# Hand tuning carried over from the user's v1 rulesmo.ini (which the first
# rebuild-from-pristine had silently dropped), plus the requested +50% reach.
# "v1" comments record the value the user had chosen themselves.
TUNING = {
    "GAHYBR": [
        ("Strength", "3333"),        # v1
        ("Cost", "0"),               # v1 (this is why click-repair does nothing)
        ("Power", "0"),              # v1 - no power drain
        ("Powered", "no"),           # v1 - works with the grid down
        ("AntiAirValue", "40"),      # v1 - AI threat weighting only
        ("Sight", "16"),             # 12 +30%, rounded up (Sight is integral)
        ("SelfHealing", "yes"),      # stands in for click-repair
    ],
    # Hybrid Tower weapons: used by GAHYBR and nothing else in all of MO.
    # Range is stock +50%: 14 -> 21, and the support beam's 15 -> 22.5.
    "HybridBolt": [("Damage", "35"), ("Range", "21"), ("Projectile", "InvisibleHighAA")],
    "HybridBoltE": [("Damage", "35"), ("Range", "21"), ("Projectile", "InvisibleHighAA")],
    "HybridBoltSupport": [("Damage", "35"), ("Range", "22.5"), ("Projectile", "InvisibleHighAA")],
    # Shin Tsurugi Decimator weapons, v1 values restored verbatim.
    # (v1 left ShinBeams itself at the stock 9.5 while every sibling went to 13.)
    "ShinBeamsE": [("Range", "13")],
    "ShinMissiles": [("Range", "13")],
    "ShinMissilesE": [("Range", "13")],
    "ShinCannons": [("Range", "13")],
    "ShinCannonsE": [("Range", "13")],
}

log = []


def say(msg):
    log.append(msg)
    print(msg)


# --------------------------------------------------------------------------
# prerequisite rewriting helpers
# --------------------------------------------------------------------------

def rewrite_and_list(value, mapping):
    """Rewrite an AND-style Prerequisite= list: a token that must now also be
    satisfiable by a clone becomes the OR-generic that covers both."""
    return ",".join(mapping.get(x, x) for x in split_list(value))


def rewrite_or_list(value, clones):
    """Rewrite an OR-style [GenericPrerequisites] value: the clone is simply
    appended next to the original, since any option satisfies the generic."""
    out = []
    for x in split_list(value):
        out.append(x)
        if x in clones:
            out.append(clones[x])
    return ",".join(out)


def build(dry=False):
    prepare()

    rules = Ini(os.path.join(PRISTINE, "rulesmo.ini"))
    art = Ini(os.path.join(PRISTINE, "artmo.ini"))

    # Must happen before classification: with the cross-faction generic
    # BARRACKS the engineers have no unique ConYard root and would be skipped.
    ENG = {"ENGINEER": "ALLRAX", "SENGINEER": "SOVRAX",
           "YENGINEER": "YURRAX", "FENGINEER": "FOERAX"}
    for e, rax in ENG.items():
        assert rules.get(e, "Prerequisite") == "BARRACKS", (e, rules.get(e, "Prerequisite"))
        rules.set_key(e, "Prerequisite", rax)

    tree = Tree(rules)
    g1, g2, skipped = tree.groups()
    say(f"分组：第1组(开Owner) {len(g1)}  第2组(克隆) {len(g2)}  跳过 {len(skipped)}")

    g2_types = [t for _, t in g2]
    g2_buildings = [t for L, t in g2 if L == "BuildingTypes"]
    clone_id = {t: P + t for t in g2_types}

    # --- name the OR-generics we need -------------------------------------
    existing = {s.upper() for s in rules.section_names()} | set(tree.generics)
    generic_for = {}
    for t in list(SIDES) + g2_buildings + list(LAB_CLONES):
        name = "ANY" + t
        assert name.upper() not in existing, f"generic name collision: {name}"
        generic_for[t] = name
    conyard_clone = {cy: FACTION[cy][2] for cy in SIDES}
    lab_clone = {b: P + b for b in LAB_CLONES}
    all_clone = dict(clone_id)
    all_clone.update(conyard_clone)
    all_clone.update(lab_clone)

    # ======================================================================
    # 1. rulesmo.ini — edits to existing entries
    # ======================================================================
    from motree import CONYARDS
    # [General] BaseUnit and [AI] BuildConst are index-based lists over the
    # stock MCVs and Construction Yards. Leave both families' Owner alone --
    # a foreign player reaches the tree through the SU MCV/yard instead.
    BASE_UNITS = {FACTION[c][0] for c in FACTION}
    g1 = [(L, t) for L, t in g1 if t not in CONYARDS and t not in BASE_UNITS]
    n_owner = n_extra = 0
    for _, t in g1:
        rules.set_key(t, "Owner", ALL12_STR)
        n_owner += 1
        for k in ("RequiredHouses", "ForbiddenHouses"):
            n_extra += rules.delete_key(t, k)
        if rules.get(t, "FactoryOwners"):
            rules.set_key(t, "FactoryOwners", ALL12_STR)
            n_extra += 1
    say(f"[rules] 开放 Owner：{n_owner} 个条目（另放开 {n_extra} 处 "
        f"RequiredHouses/ForbiddenHouses/FactoryOwners）")

    # 1b/1c. AND-style Prerequisite lines: swap gated tokens for OR-generics
    and_map = {t: generic_for[t] for t in list(SIDES) + g2_buildings
               + list(LAB_CLONES)}
    n_pre = 0
    for sec in rules.section_names():
        for key in ("Prerequisite", "Prerequisite.List0", "Prerequisite.List1",
                    "Prerequisite.List2", "Prerequisite.List3"):
            cur = rules.get(sec, key)
            if not cur:
                continue
            new = rewrite_and_list(cur, and_map)
            if new != cur:
                rules.set_key(sec, key, new)
                n_pre += 1
    say(f"[rules] 前置改写为通用前置：{n_pre} 行")

    # 1c-2. OR-style generic prerequisite values: append the clone
    n_gen = 0
    for k, v in list(rules.items("GenericPrerequisites").items()):
        new = rewrite_or_list(v, all_clone)
        if new != v:
            rules.set_key("GenericPrerequisites", k, new)
            n_gen += 1
    say(f"[rules] 通用前置追加克隆体：{n_gen} 条")

    # 1c-3. define the new OR-generics
    for t, name in generic_for.items():
        rules.set_key("GenericPrerequisites", name, f"{t},{all_clone[t]}")
    say(f"[rules] 新增通用前置定义：{len(generic_for)} 条")

    say(f"[rules] 工程师前置分家（分类前已应用）：{len(ENG)} 条")

    # 1e. hand tuning (Hybrid Tower + Decimator)
    n_tune = 0
    for sect, pairs in TUNING.items():
        assert rules.has_section(sect), f"missing section {sect}"
        for k, v in pairs:
            rules.set_key(sect, k, v)
            n_tune += 1
    say(f"[rules] 手工调参：{len(TUNING)} 个段 / {n_tune} 个键"
        f"（混合塔不耗电+射程原版+50%+视野16+自愈+对空）")

    # ======================================================================
    # 2. the new content -- appended into rulesmo.ini itself
    # ======================================================================
    su = []

    def sec(name, pairs, comment=None):
        if comment:
            su.append(f"; {comment}")
        su.append(f"[{name}]")
        su.extend(f"{k}={v}" for k, v in pairs)
        su.append("")

    su.append("")
    su.append("; ==========================================================")
    su.append("; >>> STARUNITY EX BEGIN <<<")
    su.append("; Personal expansion for Mental Omega 3.3.6.")
    su.append("; Everything below is NEW content. Generated by")
    su.append("; _MO_EX_MOD_BACKUP/tools/build_mod.py - do not hand edit.")
    su.append("; To revert: restore pristine/rulesmo.ini, or delete this file")
    su.append("; (the game then falls back to the copy inside expandmo99.mix).")
    su.append("; ==========================================================")
    su.append("")

    new_by_list = {"BuildingTypes": [], "VehicleTypes": [],
                   "InfantryTypes": [], "AircraftTypes": []}
    for cy, (_, mcv, conyard, _c, _n, _e) in FACTION.items():
        new_by_list["VehicleTypes"].append(mcv)
        new_by_list["BuildingTypes"].append(conyard)
    for L, t in g2:
        new_by_list[L].append(clone_id[t])

    beacon_clone = {u: P + u for u in BEACON_UNLOCKS}
    beacon_clone.update({u: P + u for u in BEACON_PARTNERS})
    hero_ids = [x for x in rules.list_values("InfantryTypes")
                if (rules.get(x, "Armor") or "").strip() in HERO_ARMORS
                and x not in HERO_SKIP]
    hero_clone = {u: P + u for u in hero_ids}
    new_by_list["InfantryTypes"].extend(hero_clone[u] for u in hero_ids)
    new_by_list["BuildingTypes"].append(BEACON)
    new_by_list["BuildingTypes"].extend(lab_clone[b] for b in LAB_CLONES)
    for u, L in BEACON_PARTNERS.items():
        new_by_list[L].append(beacon_clone[u])
    for u in BEACON_UNLOCKS:
        new_by_list["VehicleTypes"].append(beacon_clone[u])
    new_by_list["Projectiles"] = ["InvisibleHighAA"]
    new_by_list["SuperWeaponTypes"] = [x[0] for x in SUPERWEAPONS] + [BEACON_SW]
    n_reg = 0
    for L, vals in new_by_list.items():
        if vals:
            rules.append_to_list(L, vals)
            n_reg += len(vals)
    say(f"[rules] 注册新类型：{n_reg} 个（写进 rulesmo.ini 自己的编号列表）")

    sec("InvisibleHighAA",
        [("Inviso", "yes"), ("Image", "none"), ("SubjectToElevation", "yes"),
         ("AA", "yes"), ("AG", "yes")],
        "Hybrid Tower projectile: a copy of InvisibleHigh with AA. The stock "
        "InvisibleHigh is shared by 90 weapons and must not be touched.")

    # --- the four tech Construction Yards ---------------------------------
    for cy, (stock_mcv, mcv, conyard, cam, cn, en) in FACTION.items():
        pairs = []
        for k, v in rules.items(cy).items():
            pairs.append((k, v))
        d = dict(pairs)
        d["UIName"] = f"NAME:{conyard}"
        d["Name"] = f"Starunity {en.capitalize()} Construction Yard"
        d["Owner"] = ALL12_STR
        d.pop("RequiredHouses", None); d.pop("ForbiddenHouses", None)
        if "FactoryOwners" in d:
            d["FactoryOwners"] = ALL12_STR
        d["UndeploysInto"] = mcv
        d["TechLevel"] = "-1"
        d["AIBuildThis"] = "no"
        d["Image"] = cy                 # RULES Image -> stock art entry
        d.pop("Prerequisite", None)
        sec(conyard, list(d.items()), f"{en.capitalize()} tech Construction Yard (from {mcv})")

    # --- the four tech MCVs ------------------------------------------------
    for cy, (stock_mcv, mcv, conyard, cam, cn, en) in FACTION.items():
        d = dict(rules.items(stock_mcv).items())
        d["UIName"] = f"NAME:{mcv}"
        d["Name"] = f"Starunity {en.capitalize()} Construction Vehicle"
        d["Owner"] = ALL12_STR
        d.pop("RequiredHouses", None); d.pop("ForbiddenHouses", None)
        d["DeploysInto"] = conyard
        d["TechLevel"] = "-1"
        d["AIBuildThis"] = "no"
        d["AllowedToStartInMultiplayer"] = "no"
        d["Cost"] = "3000"
        d["Image"] = stock_mcv          # RULES Image -> stock voxel + art
        d.pop("Prerequisite", None)
        sec(mcv, list(d.items()), f"{en.capitalize()} tech MCV (support power delivery only)")

    # --- 63 clones ---------------------------------------------------------
    for L, t in g2:
        side = tree.side_of(t)
        new_id = clone_id[t]
        d = dict(rules.items(t).items())
        d["Owner"] = ALL12_STR
        d.pop("RequiredHouses", None)
        d.pop("ForbiddenHouses", None)
        if "FactoryOwners" in d:
            d["FactoryOwners"] = ALL12_STR
        d["Image"] = rules.get(t, "Image") or t
        # A clone that converts/deploys into another group-2 type must point at
        # THAT type's clone, otherwise deploying it hands back a stock unit the
        # player has no tech for (e.g. SUETNK -> stock ETNK2).
        for k in ("Convert.Deploy", "Convert.Water", "Convert.Land",
                  "Convert.Script", "UndeploysInto", "DeploysInto",
                  "UpgradesTo", "Spawns", "PowersUpBuilding"):
            if k in d:
                d[k] = ",".join(clone_id.get(x, x) for x in split_list(d[k]))

        undo_generic = {generic_for[k]: k for k in generic_for}
        pre = split_list(d.get("Prerequisite", ""))
        pre = [undo_generic.get(x, x) for x in pre]
        pre = [conyard_clone.get(x, clone_id.get(x, x)) for x in pre]
        if conyard_clone[side] not in pre:
            pre.append(conyard_clone[side])
        d["Prerequisite"] = ",".join(pre)
        d["AIBuildThis"] = "no"
        sec(new_id, list(d.items()),
            f"{SIDES[side][0]} {t} tech-tree copy - requires {conyard_clone[side]}")

    # --- Far Star Support Beacon -------------------------------------------
    rules.set_key("GenericPrerequisites", BEACON_YARD_GENERIC,
                  ",".join(FACTION[cy][2] for cy in SIDES))

    d = dict(rules.items(BEACON_DONOR))
    # the donor is a decorative map prop; make it behave like a real building
    for k in ("Insignificant", "Nominal", "Unsellable"):
        d.pop(k, None)
    d.update({
        "UIName": f"NAME:{BEACON}",
        "Name": "Far Star Support Beacon",
        "Image": BEACON_DONOR,          # 3x3 foundation + ActiveAnim come along
        "Owner": ALL12_STR,
        "Prerequisite": BEACON_YARD_GENERIC,
        "TechLevel": "1",
        "BuildCat": "Tech",
        "Armor": "concrete_b",
        "Strength": "2000",
        "Sight": "6",
        "Cost": "2500",
        "Soylent": "1250",
        "Points": "300",
        "Power": "-200",
        "Powered": "yes",
        "BaseNormal": "yes",
        "Capturable": "false",
        "AIBuildThis": "no",
        "SuperWeapons": BEACON_SW,
    })
    sec(BEACON, list(d.items()),
        "Far Star Support Beacon - buildable from any SU tech Construction "
        "Yard; carries the Knights support power and unlocks the ten units "
        "below. NB: the donor art has no Buildup=, so it pops in without a "
        "construction animation. Cosmetic only.")

    d = dict(rules.items(BEACON_SW_DONOR))
    for k in ("SW.RequiredHouses", "SW.AuxBuildings", "SW.AITargeting.Constraints"):
        d.pop(k, None)
    d.update({
        "UIName": f"NAME:{BEACON_SW}",
        "Name": "Far Star Knights Aid",
        "IsPowered": "true",            # goes offline with the grid, as asked
        "Money.Amount": BEACON_SW_COST,
        "RechargeTime": BEACON_SW_RECHARGE,
        "Range": "1.5",                 # same as MO's own 10-unit delivery
        "Deliver.Types": BEACON_SW_DELIVERS,
        "SidebarPCX": "suckngt.pcx",
        "SW.AITargeting": "none",
        "SW.UseAITargeting": "no",
        "SW.AllowAI": "no",
        "SW.AllowPlayer": "yes",
    })
    sec(BEACON_SW, list(d.items()),
        "Far Star Knights Aid - 2x Prism/Abrams/Blizzard/Paladin + 1 repair "
        "drone, 8500 credits, 15s recharge")

    # the ten stolen-tech units, plus their transform partners
    for u in BEACON_UNLOCKS + list(BEACON_PARTNERS):
        d = dict(rules.items(u))
        d["Owner"] = ALL12_STR
        d.pop("RequiredHouses", None)
        d.pop("ForbiddenHouses", None)
        if "FactoryOwners" in d:
            d["FactoryOwners"] = ALL12_STR
        d["Image"] = rules.get(u, "Image") or u
        for k in ("Convert.Deploy", "Convert.Water", "Convert.Land",
                  "Convert.Script", "UndeploysInto", "DeploysInto",
                  "UpgradesTo", "Spawns", "PowersUpBuilding"):
            if k in d:
                d[k] = ",".join(beacon_clone.get(x, x) for x in split_list(d[k]))
        d["AIBuildThis"] = "no"
        if u in BEACON_PARTNERS:
            # reached only by transforming its partner, never built directly
            d["TechLevel"] = "-1"
            d.pop("Prerequisite", None)
            note = f"{u} copy - transform partner, not buildable"
        else:
            # any faction's war factory, but only with the beacon standing
            d["Prerequisite"] = f"FACTORY,{BEACON}"
            d["TechLevel"] = "10"
            note = f"{u} copy - any war factory + {BEACON}"
        sec(beacon_clone[u], list(d.items()), note)

    # --- Allied Battle Lab copy --------------------------------------------
    for b, yard_key in LAB_CLONES.items():
        yard = conyard_clone[yard_key]
        d = dict(rules.items(b))
        d["Owner"] = ALL12_STR
        d.pop("RequiredHouses", None)
        d.pop("ForbiddenHouses", None)
        if "FactoryOwners" in d:
            d["FactoryOwners"] = ALL12_STR
        d["Image"] = rules.get(b, "Image") or b
        d["Prerequisite"] = yard          # the yard alone, nothing else
        d["AIBuildThis"] = "no"
        sec(lab_clone[b], list(d.items()),
            f"{b} copy - {yard} is the only requirement, so map INI overrides "
            f"that lock the stock branch cannot reach it")
    # let it satisfy the engine's TECH generic as well; normal players cannot
    # build it, so this changes nothing for them
    tech = split_list(rules.get("General", "PrerequisiteTech") or "")
    rules.set_key("General", "PrerequisiteTech",
                  ",".join(tech + [lab_clone[b] for b in LAB_CLONES]))

    # --- hero infantry ------------------------------------------------------
    for u in hero_ids:
        d = dict(rules.items(u))
        d["Owner"] = ALL12_STR
        d.pop("RequiredHouses", None)
        d.pop("ForbiddenHouses", None)
        if "FactoryOwners" in d:
            d["FactoryOwners"] = ALL12_STR
        d["Image"] = rules.get(u, "Image") or u
        for k in ("Convert.Deploy", "Convert.Water", "Convert.Land",
                  "Convert.Script", "UndeploysInto", "DeploysInto",
                  "UpgradesTo", "Spawns", "PowersUpBuilding"):
            if k in d:
                d[k] = ",".join(hero_clone.get(x, x) for x in split_list(d[k]))
        d["Prerequisite"] = f"BARRACKS,{BEACON}"
        d["TechLevel"] = "10"
        d["AIBuildThis"] = "no"
        sec(hero_clone[u], list(d.items()),
            f"{u} copy - any barracks + {BEACON}")
    say(f"[rules] 英雄步兵解锁：{len(hero_ids)} 个（任意兵营 + {BEACON}）")

    # --- superweapons ------------------------------------------------------
    for sw, deliver, cam, en_name, cn in SUPERWEAPONS:
        pairs = [("UIName", f"NAME:{sw}"), ("Name", en_name)]
        pairs += SW_TEMPLATE
        pairs += [("SidebarPCX", cam), ("Deliver.Types", deliver)]
        sec(sw, pairs, en_name)

    su.append("; >>> STARUNITY EX END <<<")
    rules.lines.extend(su)
    text = "\r\n".join(su)          # readable copy kept in the backup folder

    # ======================================================================
    # 3. artmo.ini — art for the new MCVs and Construction Yards
    # ======================================================================
    # No art sections are needed: every new type carries a rules Image= that
    # redirects to the stock entry, so model, cameo and foundation all follow.
    say("[art] 无需新增美术段（新类型用 rules Image= 指向原版美术条目）")

    # ======================================================================
    # 4. ra2md.csf
    # ======================================================================
    csf = Csf(os.path.join(BACKUP, "original", "ra2md.csf"))
    added = 0
    for cy, (stock_mcv, mcv, conyard, cam, cn, en) in FACTION.items():
        csf.set(f"NAME:{mcv}", f"{cn}科技基地车")
        csf.set(f"NAME:{conyard}", f"{cn}科技建造场")
        added += 2
    for sw, deliver, cam, en_name, cn in SUPERWEAPONS:
        csf.set(f"NAME:{sw}", cn)
        added += 1
    csf.set(f"NAME:{BEACON}", "远星支援信标")
    csf.set(f"NAME:{BEACON_SW}", "远星骑士团支援")
    added += 2
    say(f"[csf] 新增字符串：{added} 条")

    # ======================================================================
    # 5. MentalOmegaMaps.ini — unlock co-op for skirmish
    # ======================================================================
    maps = Ini(os.path.join(BACKUP, "original", "MentalOmegaMaps.ini"), encoding="utf-8-sig")
    killed = []
    # (a) the three Co-Op game-mode sections
    for mode in ("Co-Op Easy", "Co-Op Medium", "Co-Op Hard"):
        killed += maps.delete_lines_matching(mode, r"(HumanPlayersOnly|MultiplayerOnly)\s*=")
    n_mode = len(killed)
    # (b) every per-map section -- this is the one the client actually reads to
    #     pop "selected map can only be used on CnCNet or LAN". Clearing only
    #     the mode sections is not enough (verified in game).
    n_map_sec = 0
    for sec2 in maps.section_names():
        if sec2.lower().startswith(r"mapsmo\cooperative" + "\\") and maps.get(sec2, "MultiplayerOnly"):
            maps.delete_key(sec2, "MultiplayerOnly")
            n_map_sec += 1
    # (c) let the mission start with one player. Slot 2's half of the mission
    #     is handed to slot 1 below, so an ally house would own nothing and the
    #     engine would declare it defeated on the first frame -- which is what
    #     failed the mission. With MinPlayers=1 the slot simply stays empty.
    #     The scripted enemies are unaffected: the client builds them from each
    #     entry's own EnemyHouse0/EnemyHouse1, not from the player slots.
    # MinPlayers alone is not enough: the client auto-fills a co-op lobby up to
    # MaxPlayers, so slot 2 kept coming back as an AI ally that owned nothing
    # and was defeated on frame 1. Dropping MaxPlayers to 1 removes the slot.
    # The scripted enemies are unaffected - they come from EnemyHouse0/1, which
    # carry their own spawn positions (verified in a real spawn.ini: Multi3/
    # Multi4 had locations, the auto-filled Multi2 never did).
    n_solo = 0
    for sec2 in maps.section_names():
        if (sec2.lower().startswith(r"mapsmo\cooperative" + "\\")
                and maps.get(sec2, "MinPlayers") == "2"):
            maps.set_key(sec2, "MinPlayers", "1")
            maps.set_key(sec2, "MaxPlayers", "1")
            n_solo += 1
    say(f"[maps] 删除联机限制：模式段 {n_mode} 行 + 地图条目 {n_map_sec} 处")
    say(f"[maps] 合作地图改为单人：MinPlayers/MaxPlayers 2->1，{n_solo} 张")
    assert n_solo == 36, f"expected 36 entries, changed {n_solo}"
    assert n_mode == 6, f"expected 6 mode lines, removed {n_mode}"
    assert n_map_sec == 36, f"expected 36 map entries, cleared {n_map_sec}"

    # ======================================================================
    # 6. co-op maps — drop the engine-level multiplayer-only flag
    # ======================================================================
    # [Basic] MultiplayerOnly=1 marks the map as lobby-only. Clearing the mode
    # level flags in MentalOmegaMaps.ini is not enough while the map files
    # themselves still carry it. Verified in game: a co-op map runs offline as
    # a skirmish with one AI ally and no errors.
    coop_src = os.path.join(BACKUP, "Cooperative")
    coop_out = os.path.join(OUTPUT, "Cooperative")
    os.makedirs(coop_out, exist_ok=True)
    n_map = n_min = 0
    for fn in sorted(os.listdir(coop_src)):
        if not fn.lower().endswith(".map"):
            continue
        mp = Ini(os.path.join(coop_src, fn))
        if mp.get("Basic", "MultiplayerOnly"):
            mp.delete_key("Basic", "MultiplayerOnly")
            n_map += 1
        if mp.get("Basic", "MinPlayer") == "2":
            mp.set_key("Basic", "MinPlayer", "1")
            n_min += 1
        mp.save(os.path.join(coop_out, fn))
    say(f"[maps] 合作地图去掉 MultiplayerOnly：{n_map} / "
        f"{len(os.listdir(coop_src))} 张，[Basic] MinPlayer 2->1：{n_min} 张")

    # hand slot 2's half of every co-op mission to slot 1
    n_ev = n_ac = n_maps2 = 0
    for fn in sorted(os.listdir(coop_out)):
        if not fn.lower().endswith(".map"):
            continue
        path = os.path.join(coop_out, fn)
        mp = Ini(path, encoding="latin-1")
        touched = False
        for sect, per_slot in (("Events", 3), ("Actions", 8)):
            for start, end in mp.sections.get(sect, []):
                for i in range(start + 1, end):
                    line = mp.lines[i]
                    if COOP_P2 not in line or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    parts = val.split(",")
                    try:
                        n = int(parts[0])
                    except ValueError:
                        continue
                    hit = False
                    for j in range(n):
                        for off in range(1 + j * per_slot,
                                         min(1 + (j + 1) * per_slot, len(parts))):
                            if parts[off].strip() == COOP_P2:
                                parts[off] = COOP_P1
                                hit = True
                    if hit:
                        mp.lines[i] = key + "=" + ",".join(parts)
                        touched = True
                        if sect == "Events":
                            n_ev += 1
                        else:
                            n_ac += 1
        if touched:
            mp.save(path)
            n_maps2 += 1
    say(f"[maps] 合作任务 2 号位并入 1 号位：{n_maps2} 张图，"
        f"事件 {n_ev} 条 + 动作 {n_ac} 条")

    # ======================================================================
    # write everything out
    # ======================================================================
    dests = [OUTPUT] if dry else [OUTPUT, GAME]
    for dest in dests:
        os.makedirs(dest, exist_ok=True)
        rules.save(os.path.join(dest, "rulesmo.ini"))
        art.save(os.path.join(dest, "artmo.ini"))
        stale = os.path.join(dest, "starunity.ini")
        if os.path.exists(stale):
            os.remove(stale)          # superseded: the block now lives in rules
        csf.save(os.path.join(dest, "ra2md.csf"))
        ini_dir = os.path.join(dest, "INI")
        os.makedirs(ini_dir, exist_ok=True)
        maps.save(os.path.join(ini_dir, "MentalOmegaMaps.ini"))
        for f in sorted(os.listdir(CAMEOS)):
            shutil.copy2(os.path.join(CAMEOS, f), os.path.join(dest, f))
        coop_dest = os.path.join(dest, "MapsMO", "Cooperative")
        if os.path.isdir(coop_dest):
            for f in os.listdir(coop_out):
                shutil.copy2(os.path.join(coop_out, f), os.path.join(coop_dest, f))
    with open(os.path.join(OUTPUT, "starunity_block.ini"), "w",
              encoding="latin-1", newline="") as fh:
        fh.write(text)                # human-readable copy of the added block
    say(f"写出完成 -> {', '.join(dests)}")
    return dict(g1=g1, g2=g2, clone_id=clone_id, generic_for=generic_for)


def main():
    ap = argparse.ArgumentParser(description="Noob Edition patch generator")
    ap.add_argument("--game", required=True,
                    help="path to your Mental Omega 3.3.6 installation")
    ap.add_argument("--work", default=None,
                    help="scratch + backup directory (default: <repo>/work)")
    ap.add_argument("--dry", action="store_true",
                    help="build into work/output only, do not touch the game")
    ap.add_argument("--restore", action="store_true",
                    help="undo the patch and exit")
    args = ap.parse_args()
    configure(args)
    if args.restore:
        restore()
        return
    build(dry=args.dry)


if __name__ == "__main__":
    main()
