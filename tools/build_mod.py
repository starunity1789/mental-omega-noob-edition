"""Noob Edition patch generator for Mental Omega 3.3.6.

Ships no Mental Omega content. It reads the pristine data straight out of your
own installation, applies the Noob Edition changes and writes the result back
into the game folder. Every file it replaces is snapshotted first.

  python tools/build_mod.py --game "D:/Games/Mental Omega"   first run
  python tools/build_mod.py                   later runs (paths are remembered)
  python tools/build_mod.py --dry             build into <work>/output only
  python tools/build_mod.py --restore         put the game back exactly as it was
  python tools/validate.py                    prove nothing else moved

Optional parts, snapshotted once into <work> and rebuilt on every later run:
  --qier "<企鹅的心灵终结 v1.1 folder>"   Phobos UI features + 12 skirmish maps
  --abc  "<东方秽浪港 install>/Game"      Touhou infantry + ABC Prism Tank
Without them those parts are simply left out. See paths.py for the layout.

What it produces
  rulesmo.ini            pristine + surgical edits, then the whole new-content
                         block appended between STARUNITY EX BEGIN/END markers
  artmo.ini              pristine + art sections for the new types
  ra2md.csf              stock strings + names for the new content
  INI/MentalOmegaMaps.ini  co-op modes unlocked for skirmish (+ the QiEr maps)
  MapsMO/Cooperative/*   co-op missions playable solo
  sfatal.map             Fatal Impact: 4-hour timer, Volkov rides transports
  soundmo.ini            (+ the ABC units' sounds)
  MOAutoRepair.dll       player buildings repair themselves
  *.pcx, suyurix*        cameos (support powers, beacon, Yuri)
  optional               Phobos + SyringeEx + uimd.ini + client launch line,
                         MapsMO/qier_maps/* + SP_LIBRA.ini, expandmo93.mix + abc*.pcx
  (work only) starunity_block.ini — readable copy of the appended block

Why one file instead of an [#include]: [GenericPrerequisites] is evaluated
before an included file's "+=" registrations exist, so every ANY*=...,SU*
entry failed to parse. Verified in game: 64 warnings with the include, 0 with
everything inside rulesmo.ini.
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import paths                                             # noqa: E402

from moini import Ini                                    # noqa: E402
from motree import Tree, SIDES, ALL12_STR, split_list    # noqa: E402
from csftool import Csf                                  # noqa: E402
from mixtool import extract                              # noqa: E402
import cameo                                             # noqa: E402
import abc_port                                          # noqa: E402
import qier_maps                                         # noqa: E402

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

# Tech buildings whose capture effects the beacon also grants, so owning it
# is as good as holding all of them. Their effects are plain building tags:
#   Academy.<Kind>Veterancy   (Ares) new units of that kind come out veteran
#   InfantryGainSelfHeal / UnitsGainSelfHeal   infantry / vehicles self-repair
# The tags are read from the stock buildings at build time, not copied by
# hand. Academy.Types / Academy.Ignore are dropped: they only split vehicles
# between the Heavy Machinery Plant (land) and the Military Docks (naval),
# and together the two cover every vehicle.
TECH_DONORS = {
    "CAACAD": "科技步兵学院", "CAHMCH": "科技重机械厂", "CAAERO": "科技航空学院",
    "CADEFB": "科技防卫局", "CADOCK": "科技军事码头", "CAMACH": "科技机械维修车间",
    "CATHOSP": "科技医院",
}
TECH_EFFECT = ("Academy.InfantryVeterancy", "Academy.VehicleVeterancy",
               "Academy.AircraftVeterancy", "Academy.BuildingVeterancy",
               "InfantryGainSelfHeal", "UnitsGainSelfHeal")

# The beacon is also a Grinder (部队回收厂, Yuri's YAGRND): units walk in and
# turn into money at [General] RefundPercent. Only the behaviour tags come
# over, read from the stock building; the grinding animation is YAGRND's own
# art (SpecialAnim), which the beacon's art does not have - as wanted.
GRINDER_DONOR = "YAGRND"
GRINDER_KEYS = ("Grinding", "Cursor.Enter")
# Why the beacon also needs a SpecialAnim. On every grind the engine
# (gamemd 0x73A1E8 vehicles / 0x5198DC infantry) does DestroyNthAnim(3) - the
# building's ActiveAnim - then PlayNthAnim(10), the SpecialAnim, and brings
# the ActiveAnim back when that finishes. The donor prop's own SHP is empty:
# its whole visible model IS the ActiveAnim, and with no SpecialAnim nothing
# ever finished, so the beacon vanished after its first grind. The fix is a
# SpecialAnim that is the model's own loop played once: the model keeps
# animating through the grind, so there is still no visible grinding effect.
BEACON_SPECIAL = "SUBEACON_S"

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
# ARND / STLN / CLNT are the easter-egg action-movie commandos; not wanted.
# LIBRC is Libra's clone (天秤复制人); not wanted either.
HERO_SKIP = {"AIMORA", "ARND", "STLN", "CLNT", "LIBRC"}

# Heroes whose stock art has no cameo (campaign-only units). The clone gets
# its own art entry with a drawn cameo. It cannot just point at the stock art
# with an art-level Image=: no MO infantry does that, so it is unproven for
# SHP infantry. Instead the sprite is copied under the clone's own name and
# written loose into the game folder.
#   hero: (sprite file, cameo base, alt cameo base, label, faction colour)
HERO_CAMEOS = {
    "YURIX": ("yurix.shp", "yuriicon.pcx", "yuriuico.pcx", "尤里", "epsilon"),
}
# MO blocks its campaign-only heroes (Reznov, Krukov, ...) with a 121x build
# time; the ordinary heroes use 2x. The clones get the ordinary value.
HERO_BUILD_TIME = "2"

# Boris (鲍里斯). rulesmo.ini has no [BORIS]: MO defines him per map. The full
# MO-authored definition is in the "Revolution" challenge map (the Soviet 1
# campaign map only sets TechLevel), snapshotted into pristine/. His art,
# cameo, AKM/AKME weapons and voices are all still in the stock files.
BORIS = "BORIS"
BORIS_MAP = "c_revolution.map"
# FlareAI is the computer's flavour: no player attack cursors. Morales' Flare
# is the same airstrike marker with them.
BORIS_KEYS = {"Secondary": "Flare", "EliteSecondary": "Flare",
              "BuildLimit": "1", "BuildTimeMultiplier": HERO_BUILD_TIME}

# Morales' sniper shot hurts friends three ways, all on the shot itself:
#   AmbientDamage=300 on a railgun   everything the beam passes through
#   KillDriverWH  CellSpread .3      splash at the impact point
#   airburst KillDriverFixWH  .6     KILLS THE DRIVER of vehicles nearby
# FRIENDLY_SAFE gives a clone its own copy of the whole chain: warheads
# AffectsAllies=no, and the beam's pass-through damage dropped. It has to be
# dropped: disassembly shows gamemd's TechnoClass::DealParticleDamage (0x70CBE8)
# calls ReceiveDamage directly on every object along the beam - AffectsAllies
# only exists in DamageArea - and Ares' hook at 0x70CBB0 only skips the loop
# when AmbientDamage=0. No INI setting can spare friends from the pierce.
# The user's call (2026-09-29): the pass-through damage cannot be made
# friendly-safe (see above - the engine skips every allegiance check there),
# and the splash / driver-kill do not matter in practice, so Morales keeps his
# stock shot, friendly fire included, "as a character trait". The mechanism
# stays: {"MORALES": ("Primary", "ElitePrimary")} turns it back on.
FRIENDLY_SAFE = {}
FRIENDLY_SAFE_KEEP_PIERCE = False

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
# Slot 2 is encoded two different ways and BOTH have to be rewritten:
#   * trigger events and actions use the numeric codes 4475 / 4476
#   * TeamType / ScriptType House= fields use the strings below
# Missing the string form left reinforcement teams such as "Reznov Arrives"
# assigned to a slot that no longer exists, so the hero never spawned and the
# map's "hero is gone" lose trigger fired immediately.
COOP_P2_HOUSE = "<Player @ B>"
COOP_P1_HOUSE = "<Player @ A>"

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

# Death's Hand (死神之手, DHANDL/DHANDR), the boss of the Soviet finale
# "Soviet A2 Mission: Death's Hand" (expandmo97.mix). rulesmo.ini gives the
# hands no weapons at all; that one map arms them with DeathBolt/DeathBoltAA,
# which no unit in rulesmo.ini uses (validate.py re-checks), so tuning the
# weapons here reaches that mission and nothing else.
# User's call: damage 1, attack speed -90% (= ROF delay x10).
DEATHS_HAND_WEAPONS = ("DeathBolt", "DeathBoltAA")
DEATHS_HAND_DAMAGE = "1"
DEATHS_HAND_ROF_MUL = 10

# "Fatal Impact" (致命冲击, SFATAL.MAP, Soviet A2). The map lives in
# expandmo97.mix; a patched copy is written loose into the game folder, which
# the engine reads before the mixes. Snapshot: pristine/sfatal.map.
#  - Mission timer: [Ob1]Timer Easy/Medium/Hard start it with action 27, whose
#    parameter is SECONDS (gamemd 0x6DE5C9 multiplies it by 3*5 = 15 frames),
#    and [LOST]Timer is over fails the mission. 9600 s = 2h40m -> 4 h.
#    The [EsA] 600 s "recover" timers only top the clock back up when less
#    than 600 s are left, and [EsA-O1] 2400 s is a separate later countdown;
#    both left alone.
#  - Volkov before his transformation: the map sets [VOLKOV] Size=50 so no
#    transport takes him; back to rules' 1. Safe for the "Volkov does not
#    exist" fail triggers (event 61): Ares counts types through the house's
#    owned-type counters (HouseClass+0x5500..), which only RegisterGain /
#    RegisterLoss (0x4FF700 / 0x4FF550) touch - on creation, destruction and
#    owner change, never on entering a transport.
FATAL_MAP = "sfatal.map"
FATAL_TIMER_TRIGGERS = ("01000149", "01000151", "01000153")   # [Ob1]Timer E/M/H
FATAL_TIMER_FROM, FATAL_TIMER_TO = "9600", str(4 * 3600)
FATAL_VOLKOV_SIZE = ("50", "1")

# Player buildings repair themselves (玩家建筑自动维修): our own Syringe plugin,
# tools/autorepair/ (AutoRepair.c + build.py). Replaces MagicShiba's
# MO_ExperienceEnhancements, which was removed for its bugs; see AutoRepair.c.
AUTOREPAIR_DIR = os.path.join(HERE, "autorepair")
AUTOREPAIR_DLL = os.path.join(AUTOREPAIR_DIR, "MOAutoRepair.dll")

# Phobos (engine extension, GPL-3.0) for its UI features, taken from the
# "企鹅的心灵终结 v1.1" (Mental Omega QiEr) pack, which already runs it with MO's
# Ares 3.0: Phobos 0.5.0.0-alpha2, snapshotted into <work>/third_party/phobos/
# by --qier (paths.PHOBOS_DIR). Left out entirely when that snapshot is absent.
# - Needs SyringeEx (Phobos' own Syringe fork): with MO's Syringe 0.7.3.0 mo
#   Phobos loads, then refuses to run ("unsupported Syringe version", tested
#   in game 2026-11-05). So Syringe.exe becomes SyringeEx 0.7.2.0 - the one the
#   QiEr pack ships and runs MO with. MO's own is kept in <work>/original/.
# - SyringeEx's command line is "Syringe.exe <exe> --args=\"...\"" and it skips
#   flags it does not know, so the client config changes the way the QiEr pack
#   does it (Syringe.exe launched as the game, -SPAWN inside --args), plus the
#   -SPEEDCONTROL and -AFFINITY that the QiEr pack dropped.
# - Hooks: 1596; 93 share an address with Ares (Syringe chains those),
#   none partially overlaps Ares or MOAutoRepair (validate.py re-checks).
#   Phobos' MainLoop_FrameStep_Begin sits on the same 5 bytes as our
#   AutoRepair_MainLoop (0x55D360) - same address and size, so chained.
# - Its .patch section (245 byte patches, applied by Phobos itself) touches
#   neither our hook bytes nor the engine functions MOAutoRepair calls.
# The features are switched on in uimd.ini (pristine copy from expandmo99.mix
# + exactly the QiEr pack's keys):
# The superweapon sidebar also needs a rules switch: without
# [AudioVisual] SuperWeaponSidebar.AllowByDefault no superweapon is let in
# (seen in game: everything else on, sidebar empty). The QiEr pack also sets
# SuperWeaponSidebar.Allow=yes / Significance=1 on all 108 of its
# superweapons - identical for every one, so the default does the same job.
RULES_UI_KEYS = [
    ("AudioVisual", "SuperWeaponSidebar.AllowByDefault", "true"),
    ("GlobalControls", "SuperWeaponSidebarKeysEnabled", "yes"),   # its hotkeys
]
PHOBOS_FILES = ("Phobos.dll", "Phobos.pdb")      # pdb: readable crash logs
CLIENT_DEFS = os.path.join("Resources", "ClientDefinitions.ini")
CLIENT_LAUNCH = [                                 # [Settings]; None = delete the key
    ("GameExecutableNames", "Syringe.exe"),
    ("GameLauncherExecutableName", None),
    ("ExtraCommandLineParams",
     'gamemd.exe --args="-SPAWN -CD -SPEEDCONTROL -LOG -AFFINITY:4194303"'),
]
UIMD_KEYS = [
    ("Sidebar", [("SuperWeaponSidebar", "true"),          # 超武侧栏
                 ("SuperWeaponSidebar.Max", "10"),
                 ("SuperWeaponSidebar.MaxColumns", "3"),  # 3 列
                 ("HarvesterCounter.Show", "true"),       # 矿车计数
                 ("PowerDelta.Show", "true")]),           # 电量变化
    ("Phobos", [("MessageApplyHoverState", "true"),       # 居中消息面板 + 历史记录
                ("MessageDisplayInCenter", "true"),
                ("MessageDisplayInCenter.BoardOpacity", "40"),
                ("MessageDisplayInCenter.LabelsCount", "6"),
                ("MessageDisplayInCenter.RecordsCount", "12"),
                ("ShowPowerPlantEnhancerRange", "yes"),   # 电厂增幅范围
                ("SuperWeaponSidebar.RequiredSignificance", "0"),
                ("ToolTipDescriptions", "true")]),        # 悬停说明
    ("ToolTips", [("ExtendedToolTips", "true"),           # 扩展悬停提示
                  ("AnchoredToolTips", "true")]),
]

# --------------------------------------------------------------------------
# the installation: pristine inputs, snapshots, deploy, restore
# --------------------------------------------------------------------------
MARKER = "STARUNITY EX BEGIN"        # sentinel written into rulesmo.ini
# read out of the game's own mixes, newest first (the engine's priority)
FROM_MIX = ["rulesmo.ini", "artmo.ini", "soundmo.ini", "uimd.ini",
            FATAL_MAP, "yurix.shp", "yuriicon.pcx", "yuriuico.pcx"]
MIXES = ["expandmo%02d.mix" % n for n in (99, 98, 97, 96, 95, 94)]
# loose stock files read but never written
FROM_LOOSE = {BORIS_MAP: os.path.join("MapsMO", "Challenge", BORIS_MAP)}
# game files that are both read as input and replaced: snapshotted before
# anything is written, and the build reads the snapshot
INPUTS = ["ra2md.csf", os.path.join("INI", "MentalOmegaMaps.ini"), CLIENT_DEFS]
COOP = os.path.join("MapsMO", "Cooperative")

log = []


def say(msg):
    log.append(msg)
    print(msg)


def pristine(name):
    return os.path.join(paths.PRISTINE, name)


def original(rel):
    """The game's own copy of a file the patch replaces (snapshotted)."""
    return os.path.join(paths.ORIGINAL, rel)


def already_patched():
    p = os.path.join(paths.GAME, "rulesmo.ini")
    if not os.path.isfile(p):
        return False
    with open(p, "r", encoding="latin-1", errors="ignore") as fh:
        return MARKER in fh.read()


def load_manifest():
    if os.path.isfile(paths.MANIFEST):
        with open(paths.MANIFEST, encoding="utf-8") as fh:
            return json.load(fh)
    return {"replaced": [], "added": []}


def save_manifest(man):
    with open(paths.MANIFEST, "w", encoding="utf-8") as fh:
        json.dump({k: sorted(set(v)) for k, v in man.items()}, fh, indent=1)


def migrate_old_layout():
    """The first public release kept its snapshots in <work>/backup/. Move
    them to <work>/original/ so --restore keeps working after an update."""
    old = os.path.join(paths.WORK, "backup")
    if not os.path.isdir(old) or os.path.isfile(paths.MANIFEST):
        return
    man = load_manifest()
    moves = [(os.path.join(old, "original", "ra2md.csf"), "ra2md.csf"),
             (os.path.join(old, "original", "MentalOmegaMaps.ini"),
              os.path.join("INI", "MentalOmegaMaps.ini"))]
    coop_old = os.path.join(old, "Cooperative")
    if os.path.isdir(coop_old):
        moves += [(os.path.join(coop_old, f), os.path.join(COOP, f))
                  for f in sorted(os.listdir(coop_old))]
    for src, rel in moves:
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(original(rel)) or paths.ORIGINAL, exist_ok=True)
            shutil.copy2(src, original(rel))
            man["replaced"].append(rel)
    # what that release wrote without a snapshot: loose files the game falls
    # back from (rules/art) and its cameos
    man["added"] += ["rulesmo.ini", "artmo.ini"] + sorted(os.listdir(paths.CAMEOS))
    save_manifest(man)
    say(f"[prepare] 旧版快照 {old} 已迁移到 {paths.ORIGINAL}")


def prepare():
    """Pull pristine data out of the game and snapshot every input file the
    patch will later overwrite. Refuses to snapshot an already patched game."""
    migrate_old_layout()
    need = [n for n in FROM_MIX if not os.path.isfile(pristine(n))]
    if need:
        done, missing = extract([os.path.join(paths.GAME, m) for m in MIXES],
                                need, paths.PRISTINE)
        for n, m, sz in done:
            say(f"[prepare] 从 {os.path.basename(m)} 取出 {n}（{sz:,} 字节）")
        if missing:
            raise SystemExit(f"could not find {missing} inside the game's mix files")
    for name, rel in FROM_LOOSE.items():
        if not os.path.isfile(pristine(name)):
            src = os.path.join(paths.GAME, rel)
            if not os.path.isfile(src):
                raise SystemExit(f"missing {rel} in the game folder")
            shutil.copy2(src, pristine(name))
    game_coop = os.path.join(paths.GAME, COOP)
    inputs = INPUTS + [os.path.join(COOP, f) for f in sorted(os.listdir(game_coop))
                       if f.lower().endswith(".map")]
    todo = [rel for rel in inputs if not os.path.isfile(original(rel))]
    if todo and already_patched():
        raise SystemExit(
            "the game is already patched but these originals were never "
            f"snapshotted, so they cannot be recovered: {todo[:3]}... Restore "
            "them from a clean Mental Omega 3.3.6 install, then run again.")
    for rel in todo:
        os.makedirs(os.path.dirname(original(rel)), exist_ok=True)
        shutil.copy2(os.path.join(paths.GAME, rel), original(rel))
    if todo:
        man = load_manifest()
        man["replaced"] += todo
        save_manifest(man)
        say(f"[prepare] 快照了游戏原有文件 {len(todo)} 个 -> {paths.ORIGINAL}")


def deploy(rels):
    """Copy <work>/output/<rel> into the game. A file seen for the first time
    is snapshotted if the game has one, or recorded as added. A file an
    earlier build wrote but this one does not (an optional part dropped) is
    put back the way it was."""
    man = load_manifest()
    known = set(man["replaced"]) | set(man["added"])
    for rel in rels:
        if rel in known:
            continue
        dst = os.path.join(paths.GAME, rel)
        if os.path.isfile(dst):
            os.makedirs(os.path.dirname(original(rel)) or paths.ORIGINAL, exist_ok=True)
            shutil.copy2(dst, original(rel))
            man["replaced"].append(rel)
        else:
            man["added"].append(rel)
    save_manifest(man)                 # before touching the game
    for rel in rels:
        dst = os.path.join(paths.GAME, rel)
        os.makedirs(os.path.dirname(dst) or paths.GAME, exist_ok=True)
        shutil.copy2(os.path.join(paths.OUTPUT, rel), dst)
    dropped = sorted(known - set(rels))
    for rel in dropped:
        revert(rel, man)
    if dropped:
        say(f"[deploy] 这次不再生成、已复原：{dropped[:6]}{' …' if len(dropped) > 6 else ''}")
    stale = os.path.join(paths.GAME, "starunity.ini")
    if os.path.exists(stale):
        os.remove(stale)               # superseded: the block now lives in rules


def revert(rel, man):
    dst = os.path.join(paths.GAME, rel)
    if rel in man["replaced"]:
        shutil.copy2(original(rel), dst)
    elif os.path.isfile(dst):
        os.remove(dst)
        d = os.path.dirname(dst)
        while d != paths.GAME and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)


def restore():
    """Put the installation back exactly as it was before the first run."""
    if not os.path.isfile(paths.MANIFEST):
        raise SystemExit("nothing to restore: " + paths.MANIFEST + " is missing")
    man = load_manifest()
    for rel in sorted(set(man["replaced"]) | set(man["added"])):
        revert(rel, man)
    os.remove(paths.MANIFEST)          # the game is clean again
    say(f"[restore] 复原 {len(man['replaced'])} 个文件，删除 {len(man['added'])} 个新增文件")


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


def friendly_safe_chain(rules, weapon, out):
    """Copy a weapon and everything it fires (projectile, airburst/shrapnel
    weapons, warheads) as P+name, with friendly damage removed. `out` collects
    {new name: (kind, dict)}; returns the new weapon name."""
    new = P + weapon
    if new in out:
        return new
    assert not rules.has_section(new), f"clone name taken: {new}"
    d = dict(rules.items(weapon))
    out[new] = ("weapon", d)
    if not FRIENDLY_SAFE_KEEP_PIERCE:
        d.pop("AmbientDamage", None)
    wh = d.get("Warhead")
    if wh:
        d["Warhead"] = P + wh
        if P + wh not in out:
            w = dict(rules.items(wh))
            w["AffectsAllies"] = "no"     # Ares: AffectsOwner follows it
            out[P + wh] = ("warhead", w)
    pj = d.get("Projectile")
    if pj:
        p = dict(rules.items(pj))
        for k in ("AirburstWeapon", "ShrapnelWeapon"):
            if p.get(k):
                p[k] = friendly_safe_chain(rules, p[k], out)
        d["Projectile"] = P + pj
        out.setdefault(P + pj, ("projectile", p))
    return new


def build(dry=False):
    OUTPUT = paths.OUTPUT
    shutil.rmtree(OUTPUT, ignore_errors=True)   # output mirrors this build only
    os.makedirs(OUTPUT)
    use_abc, use_qier, use_phobos = paths.have_abc(), paths.have_qier_maps(), paths.have_phobos()
    say("[optional] 东方/秽浪港移植 %s，企鹅包地图 %s，Phobos 界面 %s" % tuple(
        "开" if x else "关（没有快照）" for x in (use_abc, use_qier, use_phobos)))

    rules = Ini(pristine("rulesmo.ini"))
    art = Ini(pristine("artmo.ini"))

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

    # 1f. Death's Hand, Soviet finale only (see DEATHS_HAND_WEAPONS)
    for w in DEATHS_HAND_WEAPONS:
        old_rof = rules.get(w, "ROF")
        rules.set_key(w, "Damage", DEATHS_HAND_DAMAGE)
        rules.set_key(w, "ROF", str(int(old_rof) * DEATHS_HAND_ROF_MUL))
    say(f"[rules] 死神之手（苏军最终关）：{'/'.join(DEATHS_HAND_WEAPONS)} 伤害 → "
        f"{DEATHS_HAND_DAMAGE}，开火间隔 ×{DEATHS_HAND_ROF_MUL}")

    # 1g. Phobos superweapon sidebar switches (see RULES_UI_KEYS)
    for section, k, v in (RULES_UI_KEYS if use_phobos else []):
        assert rules.has_section(section), section
        rules.set_key(section, k, v)
    say(f"[rules] Phobos 超武侧栏开关：{len(RULES_UI_KEYS)} 个")

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
    su.append("; tools/build_mod.py - do not hand edit.")
    su.append("; To revert: python tools/build_mod.py --restore, or delete this")
    su.append("; file (the game then falls back to the copy inside expandmo99.mix).")
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
        "Image": BEACON,                # own art entry below: donor art + cameo
    })
    # A copy of the donor's art plus a cameo. Art-level Image= keeps the
    # donor's shape (NewTheater substitution included), as MO does for its
    # own buildings (e.g. [GACNST] Image=GGCNST).
    donor_active = art.get(BEACON_DONOR, "ActiveAnim")
    art.append_section(BEACON, list(art.items(BEACON_DONOR).items()) +
                       [("Image", BEACON_DONOR), ("CameoPCX", "sucbcon.pcx"),
                        ("AltCameoPCX", "sucbcon.pcx"),
                        ("SpecialAnim", BEACON_SPECIAL),
                        ("SpecialAnimDamaged", BEACON_SPECIAL)])
    # the model's own loop, played once (see BEACON_SPECIAL)
    special = dict(art.items(donor_active))
    special["LoopCount"] = "1"
    art.append_section(BEACON_SPECIAL, list(special.items()))
    rules.append_to_list("Animations", [BEACON_SPECIAL])
    tech = {}
    for donor in TECH_DONORS:
        for k, v in rules.items(donor).items():
            if k in TECH_EFFECT:
                tech[k] = str(max(float(v), float(tech.get(k, 0)))).rstrip("0").rstrip(".")
    assert set(tech) == set(TECH_EFFECT), sorted(set(TECH_EFFECT) - set(tech))
    d.update(tech)
    say(f"[rules] 信标兼任 {len(TECH_DONORS)} 个科技建筑：{tech}")
    grind = {k: rules.get(GRINDER_DONOR, k) for k in GRINDER_KEYS}
    assert all(grind.values()), grind
    d.update(grind)
    say(f"[rules] 信标兼任部队回收厂（{GRINDER_DONOR}）：{grind}，"
        f"退款 {rules.get('General', 'RefundPercent')}，无回收动画")
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
    boris_map = Ini(pristine(BORIS_MAP))
    assert boris_map.get(BORIS, "Primary"), f"{BORIS_MAP} has no full [{BORIS}]"
    assert not rules.has_section(BORIS), "MO now defines BORIS itself - revisit"
    hero_src = {u: dict(rules.items(u)) for u in hero_ids}
    hero_src[BORIS] = dict(boris_map.items(BORIS), **BORIS_KEYS)
    hero_clone[BORIS] = P + BORIS
    rules.append_to_list("InfantryTypes", [P + BORIS])
    safe = {}
    hero_files = {}                     # loose files for the game folder
    for u in hero_src:
        d = hero_src[u]
        d["Owner"] = ALL12_STR
        d.pop("RequiredHouses", None)
        d.pop("ForbiddenHouses", None)
        if "FactoryOwners" in d:
            d["FactoryOwners"] = ALL12_STR
        d["Image"] = rules.get(u, "Image") or u
        if u in HERO_CAMEOS:
            shp, base, alt, label, fac = HERO_CAMEOS[u]
            own = hero_clone[u]
            assert not art.get(d["Image"], "CameoPCX"), f"{u} has a cameo now - revisit"
            with open(pristine(shp), "rb") as fh:
                hero_files[own.lower() + ".shp"] = fh.read()
            pcx = {}
            for tag, src in (("icon", base), ("uico", alt)):
                name = f"{own.lower()}{tag}.pcx"
                tmp = os.path.join(OUTPUT, name)
                cameo.relabel_icon(pristine(src), label, fac, tmp)
                with open(tmp, "rb") as fh:
                    hero_files[name] = fh.read()
                pcx[tag] = name
            art.append_section(own, list(art.items(d["Image"]).items()) +
                               [("CameoPCX", pcx["icon"]), ("AltCameoPCX", pcx["uico"])])
            d["Image"] = own
        elif not art.get(d["Image"], "CameoPCX"):
            say(f"[rules] 注意：英雄 {u} 没有图标（加进 HERO_CAMEOS 可以画一个）")
        for k in ("Convert.Deploy", "Convert.Water", "Convert.Land",
                  "Convert.Script", "UndeploysInto", "DeploysInto",
                  "UpgradesTo", "Spawns", "PowersUpBuilding"):
            if k in d:
                d[k] = ",".join(hero_clone.get(x, x) for x in split_list(d[k]))
        d["Prerequisite"] = f"BARRACKS,{BEACON}"
        d["TechLevel"] = "10"
        d["AIBuildThis"] = "no"
        d["SelfHealing"] = "yes"
        if "BuildTimeMultiplier" in d:
            d["BuildTimeMultiplier"] = HERO_BUILD_TIME
        for k in FRIENDLY_SAFE.get(u, ()):
            d[k] = friendly_safe_chain(rules, d[k], safe)
        sec(hero_clone[u], list(d.items()),
            f"{u} copy - any barracks + {BEACON}")
    for name, (kind, d) in safe.items():
        sec(name, list(d.items()), f"friendly-safe {kind} copy (FRIENDLY_SAFE)")
    rules.append_to_list("Warheads", [n for n, (k, _) in safe.items() if k == "warhead"])
    rules.append_to_list("Projectiles", [n for n, (k, _) in safe.items() if k == "projectile"])
    say(f"[rules] 英雄步兵解锁：{len(hero_src)} 个（任意兵营 + {BEACON}，含从挑战地图"
        f"复原的鲍里斯）；不伤友军复制链 {len(safe)} 段：{sorted(safe)}")

    # --- superweapons ------------------------------------------------------
    for sw, deliver, cam, en_name, cn in SUPERWEAPONS:
        pairs = [("UIName", f"NAME:{sw}"), ("Name", en_name)]
        pairs += SW_TEMPLATE
        pairs += [("SidebarPCX", cam), ("Deliver.Types", deliver)]
        sec(sw, pairs, en_name)

    # --- Touhou infantry ported from 东方秽浪港 (see abc_port.py) -----------
    existing = ({s.upper() for s in rules.section_names()} |
                {s.upper() for s in art.section_names()})
    if use_abc:
        abc = abc_port.build(ALL12_STR, existing, rules.items)
    else:
        abc = dict(rules={}, art={}, sounds={}, registrations={}, strings={},
                   mix=None, mix_files=[], cameos={}, units=[], vehicles=[])
    for L, vals in abc["registrations"].items():
        if vals:
            rules.append_to_list(L, vals)
    su.append("; ---- Touhou infantry from ABC (abc_port.py) ----")
    for name, d in abc["rules"].items():
        sec(name, list(d.items()))
    for name, d in abc["art"].items():
        art.append_section(name, list(d.items()))
    if use_abc:
        say(f"[abc] 东方步兵 {len(abc['units'])} 个（任意兵营 + {BEACON}）+ 载具 "
            f"{len(abc['vehicles'])} 辆（任意战车工厂 + {BEACON}），"
            f"规则 {len(abc['rules'])} 段 / 美术 {len(abc['art'])} 段 / "
            f"音效 {len(abc['sounds'])} 段 / 资源包 {len(abc['mix_files'])} 个文件")

    su.append("; >>> STARUNITY EX END <<<")
    rules.lines.extend(su)
    text = "\r\n".join(su)          # readable copy kept in the backup folder

    # ======================================================================
    # 3. artmo.ini — art for the new MCVs and Construction Yards
    # ======================================================================
    # Clones carry a rules Image= that redirects to the stock entry, so model,
    # cameo and foundation all follow. Only the beacon (its donor prop has no
    # cameo) and the ABC infantry get art sections of their own, added above.
    say("[art] 克隆体沿用原版美术条目；新增美术段：信标 1 个 + 东方步兵 "
        f"{len(abc['art'])} 个")

    # ======================================================================
    # 4. ra2md.csf
    # ======================================================================
    csf = Csf(original("ra2md.csf"))
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
    for label, value in abc["strings"].items():
        csf.set(label, value)
        added += 1
    say(f"[csf] 新增字符串：{added} 条")

    # ======================================================================
    # 5. MentalOmegaMaps.ini — unlock co-op for skirmish
    # ======================================================================
    maps = Ini(original(os.path.join("INI", "MentalOmegaMaps.ini")), encoding="utf-8-sig")
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
    # (d) 12 skirmish maps from the QiEr pack (qier_maps.py): 3 reworked
    #     classics + 9 special-event maps. MO units only; the two 决战山巅
    #     maps [#include] SP_LIBRA.ini, deployed to the game root.
    qier_files = qier_maps.build(maps) if use_qier else {}
    if use_qier:
        say(f"[maps] 企鹅包地图：{len(qier_maps.MAPS)} 张登记到 [MultiMaps]，"
            f"部署到 MapsMO\\{qier_maps.FOLDER}\\ + {', '.join(qier_maps.EXTRA_FILES)}")

    # ======================================================================
    # 6. co-op maps — drop the engine-level multiplayer-only flag
    # ======================================================================
    # [Basic] MultiplayerOnly=1 marks the map as lobby-only. Clearing the mode
    # level flags in MentalOmegaMaps.ini is not enough while the map files
    # themselves still carry it. Verified in game: a co-op map runs offline as
    # a skirmish with one AI ally and no errors.
    # Every step below is idempotent, so already patched maps come out
    # unchanged (counts 0).
    coop_src = original(COOP)
    coop_out = os.path.join(OUTPUT, COOP)
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
    n_ev = n_ac = n_house = n_maps2 = 0
    for fn in sorted(os.listdir(coop_out)):
        if not fn.lower().endswith(".map"):
            continue
        path = os.path.join(coop_out, fn)
        mp = Ini(path, encoding="latin-1")
        touched = False
        # House=<Player @ B> on TeamTypes / ScriptTypes. Slots C, D and E are
        # the scripted enemies and must be left alone.
        for i, line in enumerate(mp.lines):
            if COOP_P2_HOUSE in line and line.split("=", 1)[0].strip() == "House":
                mp.lines[i] = line.replace(COOP_P2_HOUSE, COOP_P1_HOUSE)
                n_house += 1
                touched = True
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
        f"事件 {n_ev} 条 + 动作 {n_ac} 条 + 小队归属 {n_house} 条")

    # ======================================================================
    # 6b. Fatal Impact — 4-hour mission timer, Volkov may ride transports
    # ======================================================================
    fatal = Ini(pristine(FATAL_MAP))
    n_timer = 0
    for tid in FATAL_TIMER_TRIGGERS:
        parts = fatal.get("Actions", tid).split(",")
        hits = [i for i in range(1, 1 + int(parts[0]) * 8, 8)
                if parts[i] == "27" and parts[i + 2] == FATAL_TIMER_FROM]
        assert len(hits) == 1, (tid, parts)
        parts[hits[0] + 2] = FATAL_TIMER_TO
        fatal.set_key("Actions", tid, ",".join(parts))
        n_timer += 1
    assert fatal.get("VOLKOV", "Size") == FATAL_VOLKOV_SIZE[0]
    fatal.set_key("VOLKOV", "Size", FATAL_VOLKOV_SIZE[1])
    fatal.save(os.path.join(OUTPUT, FATAL_MAP))
    say(f"[maps] 致命冲击：主任务计时 {n_timer} 处 {FATAL_TIMER_FROM}→{FATAL_TIMER_TO} 秒"
        f"（4 小时），变身前沃尔科夫体积 {FATAL_VOLKOV_SIZE[0]}→{FATAL_VOLKOV_SIZE[1]}（可上载具）")

    # ======================================================================
    # 7. soundmo.ini — the ABC units' sound events
    # ======================================================================
    # MO normally reads soundmo.ini from expandmo99.mix; a loose copy in the
    # game folder takes precedence, so it is pristine + the ABC block.
    sound = Ini(pristine("soundmo.ini"))
    sound.append_to_list("SoundList", list(abc["sounds"]))
    for name, d in abc["sounds"].items():
        sound.append_section(name, list(d.items()))
    say(f"[sound] 新增音效事件：{len(abc['sounds'])} 条")

    # ======================================================================
    # 8. MOAutoRepair.dll — rebuilt from source when zig is installed
    # ======================================================================
    sys.path.insert(0, AUTOREPAIR_DIR)
    import build as autorepair_build
    try:
        import ziglang  # noqa: F401
        autorepair_build.build()
        say("[plugin] 玩家建筑自动维修插件 MOAutoRepair.dll 已从源码编译并通过结构检查")
    except ImportError:
        autorepair_build.check()
        say("[plugin] 没装 ziglang，用仓库里编好的 MOAutoRepair.dll（结构检查通过）")

    # ======================================================================
    # 9. uimd.ini + Phobos — the Phobos UI features (see PHOBOS_FILES)
    # ======================================================================
    if use_phobos:
        ui = Ini(pristine("uimd.ini"))
        n_ui = 0
        for section, pairs in UIMD_KEYS:
            if ui.has_section(section):
                for k, v in pairs:
                    ui.set_key(section, k, v)
            else:
                ui.append_section(section, pairs)
            n_ui += len(pairs)
        assert b"SyringeEx" in open(paths.SYRINGE_EX, "rb").read(), paths.SYRINGE_EX
        client = Ini(original(CLIENT_DEFS))
        for k, v in CLIENT_LAUNCH:
            assert client.get("Settings", k) is not None, f"[Settings] {k} missing"
            if v is None:
                client.delete_key("Settings", k)
            else:
                client.set_key("Settings", k, v)
        say(f"[phobos] uimd.ini 打开 {n_ui} 个 Phobos 界面开关；部署 {', '.join(PHOBOS_FILES)}；"
            "加载器换 SyringeEx 0.7.2.0，客户端启动参数改为 SyringeEx 语法")

    # ======================================================================
    # write everything into <work>/output (laid out like the game folder),
    # then copy it into the game
    # ======================================================================
    def out(rel):
        p = os.path.join(OUTPUT, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        written.add(rel)
        return p

    written = set()
    rules.save(out("rulesmo.ini"))
    art.save(out("artmo.ini"))
    csf.save(out("ra2md.csf"))
    maps.save(out(os.path.join("INI", "MentalOmegaMaps.ini")))
    for f in sorted(os.listdir(paths.CAMEOS)):
        shutil.copy2(os.path.join(paths.CAMEOS, f), out(f))
    if use_abc:                                  # otherwise identical to stock
        sound.save(out("soundmo.ini"))
    written.add(FATAL_MAP)                       # saved in 6b
    written |= {os.path.join(COOP, f) for f in os.listdir(coop_out)}
    shutil.copy2(AUTOREPAIR_DLL, out(os.path.basename(AUTOREPAIR_DLL)))
    for f, b in hero_files.items():              # the pcx are already there
        with open(out(f), "wb") as fh:
            fh.write(b)
    if use_phobos:
        ui.save(out("uimd.ini"))
        for f in PHOBOS_FILES:
            shutil.copy2(os.path.join(paths.PHOBOS_DIR, f), out(f))
        shutil.copy2(paths.SYRINGE_EX, out("Syringe.exe"))
        client.save(out(CLIENT_DEFS))
    if use_abc:
        with open(out(abc_port.MIX_NAME), "wb") as fh:
            fh.write(abc["mix"])
        for f, b in abc["cameos"].items():
            with open(out(f), "wb") as fh:
                fh.write(b)
    for rel, src in qier_files.items():
        shutil.copy2(src, out(rel))
    with open(os.path.join(OUTPUT, "starunity_block.ini"), "w",
              encoding="latin-1", newline="") as fh:
        fh.write(text)                # human-readable copy, never deployed
    if dry:
        say(f"写出完成 -> {OUTPUT}（--dry：没动游戏）")
    else:
        deploy(sorted(written))
        say(f"写出完成 -> {OUTPUT}，并部署 {len(written)} 个文件到 {paths.GAME}")
    return dict(g1=g1, g2=g2, clone_id=clone_id, generic_for=generic_for)


def main():
    ap = argparse.ArgumentParser(description="Noob Edition patch generator")
    paths.add_args(ap)
    ap.add_argument("--dry", action="store_true",
                    help="build into <work>/output only, do not touch the game")
    ap.add_argument("--restore", action="store_true",
                    help="put the game back exactly as it was, then exit")
    ap.add_argument("--qier", metavar="DIR",
                    help="snapshot Phobos + the 12 maps from the 企鹅的心灵终结 v1.1 folder")
    ap.add_argument("--abc", metavar="DIR",
                    help="snapshot the Touhou port from 东方秽浪港's Game folder")
    args = ap.parse_args()
    paths.configure(args, remember=True)
    if args.restore:
        restore()
        return
    prepare()
    if args.qier:
        qier_maps.extract(os.path.abspath(args.qier))
    if args.abc:
        abc_port.extract(os.path.abspath(args.abc))
    build(dry=args.dry)


if __name__ == "__main__":
    main()
