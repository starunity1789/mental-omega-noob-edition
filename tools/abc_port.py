"""Touhou infantry from 《东方秽浪港 ~ Ambitions Behind Corpse.》 (ABC) for MO EX.

Ten hero-style infantry are lifted out of ABC with everything they depend on
(weapons, warheads, projectiles, animations, particles, sounds, sprites) and
renamed into a private namespace, so nothing in Mental Omega is touched.

Two stages:

  build_mod.py --abc "<ABC>/Game"   one-off: read the ABC install (its MIX
                                    files are Blowfish-encrypted) and snapshot
                                    only what the units need into <work>/abc_source/
  build_mod.py                      calls build() on every run; it reads nothing
                                    but <work>/abc_source/ (skipped if absent)

Naming
  rules types  ABC_<source id>   (hashed to fit Ares' 24-character type limit)
  art entries  ABPnnnnn          (every art alias gets its own copy)
  sounds       ABCS_<source id>, samples ABSnnnnn.wav
  cameos       ABCnnnnN/E.pcx    (MO draws PCX cameos; SHP cameos with a
                                  custom palette come out purple)
  assets       expandmo93.mix

Why the MIX index is sorted as SIGNED int32: the engine binary-searches the
index with signed compares. The first port sorted it unsigned, so every file
whose name hash had the top bit set was unfindable - Youmu's and Yuyuko's
bodies, a dozen cameos and assorted weapon animations (the Alice crash).
"""
import base64
import collections
import hashlib
import json
import os
import re
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths                                             # noqa: E402

# Source id -> in-game Chinese name. Only these are ported; ABC's zombies,
# the Yuri variant and the Soviet/Epsilon commandos are deliberately left out.
UNITS = {
    "CIRNO":   "琪露诺",
    "ALICE":   "爱丽丝·玛格特罗伊德",
    "TENSHI":  "比那名居天子",
    "REMILIA": "蕾米莉亚·斯卡雷特",
    "KOISHI":  "古明地恋",
    "KOISHIX": "古明地觉",        # reworked into a healer, see SATORI below
    "YOUMU":   "魂魄妖梦",
    "YUYUKO":  "西行寺幽幽子",
    "YUKARI":  "八云紫（步行）",
    "CYUKARI": "八云紫（隙间）",
}
PREREQ = "BARRACKS,SUBEACON"        # any faction's barracks + Far Star beacon

# Vehicles, built at any faction's war factory + the beacon. Unlike the
# infantry they come with explicit stats from the user instead of a multiplier.
VEHICLES = {"SREF": "光棱坦克（秽浪港）"}
VEHICLE_PREREQ = "FACTORY,SUBEACON"
# Stats the user set explicitly; they win over STRENGTH_MUL.
OVERRIDES = {
    "SREF": {"Speed": "6", "Strength": "350"},
    "CIRNO": {"Strength": "900"},     # "armour x2": ABC 225 -> x2 port -> x2 again
}

# Cirno's anti-air ice laser: her own copy of ABC's IFV laser (Koishi's elite
# weapon uses the original, so it is not edited in place). Buffed twice at the
# user's request, each time range +33% and damage +100%: 9/50 -> 12/100 -> 16/200.
CIRNO_LASER = "CirnoLaser"
CIRNO_LASER_FROM = "CirnoIFVAA"
CIRNO_LASER_RANGE_MUL = 16 / 9            # (4/3)^2
CIRNO_LASER_DAMAGE_MUL = 4                # 2^2
# body, turret(s), barrel - whichever exist. Charge / multi turrets
# (TurretCount=N, e.g. the Prism Tank's 4 charge stages) load one model per
# stage: <img>tur, <img>tur1 ... <img>tur(N-1). Missing any of them left the
# whole tank invisible in game.
VOXEL_PARTS = ("", "tur", "barl") + tuple(f"tur{i}" for i in range(1, 10))
# Hit points of every ported unit (the ten + the Shanghai doll) vs. ABC.
STRENGTH_MUL = 2

# Satori Komeiji (古明地觉): ABC's campaign Koishi variant turned into a medic.
# Koishi's sprite drawn through a colour-inverted copy of the unit palette
# (lossless: the SHP pixels are untouched), MO's Field Medic weapons with
# the fire rate x6 (x3, then doubled again), and the medic's auto-heal guard
# behaviour.
SATORI = "KOISHIX"
SATORI_ART = "ABPSATORI"
SATORI_PAL = "absatori"             # -> absatori<theater>.pal
SATORI_ROF_DIV = 6
SATORI_WEAPONS = {                  # unit key -> (new weapon, MO stock weapon)
    "Primary": ("ABC_SatoriHeal", "Heal"),
    "ElitePrimary": ("ABC_SatoriHeal", "Heal"),
    "Secondary": ("ABC_SatoriHeal2", "Heal2"),        # used when riding open-topped
    "EliteSecondary": ("ABC_SatoriHeal2", "Heal2"),
}
# Range 11 (the medic's is 3) WITH the medic's area guard, guard range = range.
# Tested both ways in game:
#  - medic range 3 + area guard: she chased patients across the map. Healers
#    look for patients within the global [General] HealScanRadius=10 (cannot
#    be touched without changing the stock medic), and with range 3 she had
#    to walk to every one of them.
#  - range 11, no area guard: she barely healed on her own - the engine only
#    goes looking for patients in area guard.
# Range 11 > the 10-cell scan, so every patient she finds is already in range
# and she can heal it from where she stands.
#  - range 11 + area guard + guard range 11: she still wandered off, so the
#    guard range (how far area guard lets her stray) is cut to 4 (user's call).
SATORI_RANGE = "11"
SATORI_GUARD_RANGE = "4"
SATORI_KEYS = {"Name": "Satori Komeiji", "Cost": "900", "Soylent": "450",
               "OpenTransportWeapon": "1", "IsSelectableCombatant": "no",
               "DefaultToGuardArea": "yes", "NoSelfGuardArea": "yes",
               "GuardRange": SATORI_GUARD_RANGE}
SATORI_NO_KEYS = ()
MIX_NAME = "expandmo93.mix"
THEATERS = ["tem", "sno", "urb", "des", "lun", "ubn"]

REGS = ["InfantryTypes", "VehicleTypes", "AircraftTypes", "Animations",
        "Particles", "ParticleSystems", "Warheads"]

# Typed references. Scalars such as Armor=Flak are never remapped.
RR = set("Primary Secondary ElitePrimary EliteSecondary DeathWeapon OccupyWeapon "
         "EliteOccupyWeapon OccupierWeapon DeployWeapon Weapon Warhead Projectile "
         "AirburstWeapon ShrapnelWeapon AttachedParticleSystem DamageParticleSystems "
         "HoldsWhat SpawnsParticle Spawns DebrisTypes SpawnsParticleSystem Particle "
         "NextParticle".lower().split())
AR = set("AnimList Explosion DebrisAnims AssaultAnim Anim TrailerAnim Trailer Next "
         "ExpireAnim SpawnAnim Wake SplashList InfDeathAnim".lower().split())
SR = set("Report StartSound StopSound VoiceSelect VoiceMove VoiceAttack VoiceFeedback "
         "VoiceSpecialAttack VoiceSecondaryWeaponAttack DieSound CreateSound CrushSound "
         "ChronoInSound ChronoOutSound EnterWaterSound LeaveWaterSound CrashingSound "
         "ImpactLandSound AuxSound1 AuxSound2".lower().split())
WEAPON_N = re.compile(r"(elite)?weapon\d+")   # multi-weapon units: Weapon1=, EliteWeapon1=


def ref_domain(kl):
    """Which table a lower-cased key refers into: rules, art, sound or None."""
    if kl in RR or WEAPON_N.fullmatch(kl):
        return "r"
    return "a" if kl in AR else "s" if kl in SR else None


# Source build/ownership gates, replaced by PREREQ.
GATES = ("Prerequisite", "RequiresStolen", "FactoryOwners", "RequiredHouses",
         "ForbiddenHouses")

# Source types that are key-for-key identical to MO's own; referenced by
# their stock names instead of being copied (validate.py re-proves identity).
SHARED = {"Spark", "SparkSys"}

INF_DEATH = {"2": "InfantryExplode", "4": "FlamingInfantry", "6": "InfantryHeadPop",
             "7": "InfantryNuked", "8": "InfantryVirus", "9": "InfantryMutate",
             "10": "InfantryBrute"}


# ---------------------------------------------------------------------------
# small format helpers
# ---------------------------------------------------------------------------

def mix_id(name):
    n = name.upper().encode("ascii")
    a = len(n) & -4
    if len(n) & 3:
        n += bytes([len(n) - a]) + bytes([n[a]]) * (3 - (len(n) & 3))
    return zlib.crc32(n) & 0xFFFFFFFF


def signed(i):
    return i - (1 << 32) if i & 0x80000000 else i


def write_mix(files):
    """Unencrypted RA2 MIX. Index sorted by SIGNED id - see module docstring."""
    entries = sorted(((mix_id(n), n, b) for n, b in files.items()),
                     key=lambda e: signed(e[0]))
    ids = [e[0] for e in entries]
    assert len(set(ids)) == len(ids), "MIX hash collision"
    body = sum(len(b) for _, _, b in entries)
    out = [struct.pack("<IHI", 0, len(entries), body)]
    pos = 0
    for ident, _, blob in entries:
        out.append(struct.pack("<III", ident, pos, len(blob)))
        pos += len(blob)
    out += [b for _, _, b in entries]
    return b"".join(out)


def ini_parse(text):
    """Engine-style read: first section occurrence merges, last key wins."""
    out = {}
    cur = None
    for line in text.splitlines():
        line = line.split(";", 1)[0].strip()
        if line.startswith("[") and "]" in line:
            cur = line[1:line.index("]")].strip()
            out.setdefault(cur, {})
        elif cur is not None and "=" in line:
            k, v = line.split("=", 1)
            out[cur][k.strip()] = v.strip()
    return out


def tokens(v):
    return [x.strip() for x in v.split(",") if x.strip()]


def type_id(prefix, name):
    """Ares type IDs are capped at 24 chars; long names get a stable hash tail."""
    cand = prefix + name
    if len(cand) <= 24:
        return cand
    tail = hashlib.sha256(cand.encode("ascii")).hexdigest()[:6]
    return (prefix + name)[:24 - 7] + "_" + tail


def shp_frame(data, index=0):
    """Decode one frame of a TS/RA2 SHP to (w, h, bytes) on its full canvas."""
    _, fw, fh, count = struct.unpack_from("<4H", data)
    x, y, w, h, fmt = struct.unpack_from("<4HB", data, 8 + index * 24)
    pos, = struct.unpack_from("<I", data, 8 + index * 24 + 20)
    canvas = bytearray(fw * fh)
    if not (pos and w and h):
        return fw, fh, bytes(canvas)
    for row in range(h):
        line = []
        if fmt == 3:
            n, = struct.unpack_from("<H", data, pos)
            end = pos + n
            pos += 2
            while pos < end:
                c = data[pos]; pos += 1
                if c:
                    line.append(c)
                else:
                    line.extend([0] * data[pos]); pos += 1
        elif fmt == 2:
            n = struct.unpack_from("<H", data, pos)[0] - 2
            pos += 2
            line = list(data[pos:pos + n]); pos += n
        else:
            line = list(data[pos:pos + w]); pos += w
        assert len(line) == w, (len(line), w)
        o = (y + row) * fw + x
        canvas[o:o + w] = bytes(line)
    return fw, fh, bytes(canvas)


def encode_shp(w, h, pixels, frames=1):
    off = 8 + 24 * frames
    hdr = struct.pack("<4H", 0, w, h, frames)
    for i in range(frames):
        hdr += struct.pack("<4HB11xI", 0, 0, w, h, 1, off + i * w * h)
    return hdr + bytes(pixels) * frames


# ---------------------------------------------------------------------------
# dependency closure (shared by extract and build)
# ---------------------------------------------------------------------------

class Closure:
    def __init__(self, R, A, S):
        self.T = {"r": R, "a": A, "s": S}
        self.canon = {d: {k.lower(): k for k in t} for d, t in self.T.items()}
        self.kinds = {v.lower(): k for k in REGS for v in R.get(k, {}).values()}
        self.sel = {d: set() for d in self.T}
        self.missing = []
        self.images = set()
        self.anims = set()
        self.seqs = set()
        self.sprite_images = set()
        self._patch_source()
        q = collections.deque()
        self.q = q
        for u in list(UNITS) + list(VEHICLES):
            self.add("r", u)
        while q:
            self._visit(*q.popleft())
        for n in self.sel["r"]:
            s = R[n]
            if "Verses" in s:
                self.kinds[n.lower()] = "Warheads"
            elif "BehavesLike" in s:
                self.kinds[n.lower()] = "ParticleSystems" if "HoldsWhat" in s else "Particles"
        self.technos = {n for n in self.sel["r"] if "UIName" in R[n]}
        self.techno_images = {self.c("a", R[n].get("Image", n)) for n in self.technos}

    def _patch_source(self):
        R, S = self.T["r"], self.T["s"]
        # Yukari's campaign armament is switched on by map overrides; the
        # global rules only carry a FakeP placeholder.
        for u in ("YUKARI", "CYUKARI"):
            R[u].update(Primary="YukariP", ElitePrimary="YukariP",
                        Secondary="YukariATP", EliteSecondary="YukariATP")
        # Cirno's ice laser is an IFV turret weapon in ABC (IFVMode=7 ->
        # [FV] Weapon8). MO has no IFV, so she carries it herself: it replaces
        # her weaker ground-only laser (CirnoIFV, range 7) as secondary.
        laser = dict(R[CIRNO_LASER_FROM])
        laser["Range"] = f"{float(laser['Range']) * CIRNO_LASER_RANGE_MUL:g}"
        laser["Damage"] = str(int(laser["Damage"]) * CIRNO_LASER_DAMAGE_MUL)
        R[CIRNO_LASER] = laser
        self.canon["r"][CIRNO_LASER.lower()] = CIRNO_LASER
        R["CIRNO"].update(Secondary=CIRNO_LASER, EliteSecondary=CIRNO_LASER)
        # Satori's weapons are MO's (added in build()); drop Koishi's so the
        # closure does not drag DaggerX / SkyPEPS along.
        R[SATORI].update({k: "" for k in SATORI_WEAPONS})
        # The doll launcher's warhead belongs to a house type MO does not have.
        R["ABCSpawnerWH"] = {"Verses": ",".join(["100%"] * 11), "AffectsAllies": "no"}
        self.canon["r"]["abcspawnerwh"] = "ABCSpawnerWH"
        R["ShanghaiLauncher"]["Warhead"] = "ABCSpawnerWH"
        # Undefined sound event in the source.
        if "FeixiangR" not in S:
            R["Feixiang"]["Report"] = "None"

    def c(self, d, name):
        return self.canon[d].get(name.lower(), name)

    def add(self, d, name, why=""):
        if not name or name.lower() in ("none", "<none>", "yes", "no"):
            return
        name = self.c(d, name)
        if name in self.sel[d] or (d == "r" and name in SHARED):
            return
        if name not in self.T[d]:
            if d == "a":                       # bare SHP with no art section
                self.T[d][name] = {}
                self.canon[d][name.lower()] = name
            else:
                self.missing.append((d, name, why))
                return
        self.sel[d].add(name)
        self.q.append((d, name))

    def _visit(self, d, name):
        R, A = self.T["r"], self.T["a"]
        sec = self.T[d][name]
        if d == "r":
            if "UIName" in sec or self.kinds.get(name.lower()) in (
                    "InfantryTypes", "VehicleTypes", "AircraftTypes", "Particles"):
                img = self.c("a", sec.get("Image", name))
                self.images.add(img)
                self.add("a", img, name)
            if "Image" in sec and "UIName" not in sec and sec["Image"].lower() != "none":
                img = self.c("a", sec["Image"])
                self.images.add(img)
                self.sprite_images.add(img)
                self.add("a", img, name)
            if "InfDeath" in sec and sec["InfDeath"] in INF_DEATH:
                anim = R["General"][INF_DEATH[sec["InfDeath"]]]
                sec["InfDeathAnim"] = anim
        for k, v in list(sec.items()):
            kl = k.lower()
            dom = ref_domain(kl)
            if dom == "r":
                for x in tokens(v):
                    self.add("r", x, f"{name}.{k}")
            elif dom == "a":
                for x in tokens(v):
                    x = self.c("a", x)
                    self.anims.add(x)
                    self.add("a", x, f"{name}.{k}")
            elif dom == "s":
                for x in tokens(v):
                    self.add("s", x, f"{name}.{k}")
            elif d == "a" and kl == "sequence":
                x = self.c("a", v)
                self.seqs.add(x)
                self.add("a", x, f"{name}.Sequence")
        if d == "a":
            if "Damage" in sec and "Warhead" not in sec:
                sec["Warhead"] = "Flame"
                self.add("r", "Flame", "anim damage default")
            if "MakeInfantry" in sec:
                u = tokens(R["General"]["AnimToInfantry"])[int(sec["MakeInfantry"])]
                self.add("r", u, "MakeInfantry")
            if name not in self.seqs:
                self.images.add(name)

    # every file the build will need, by source name
    def asset_names(self):
        A = self.T["a"]
        need = {"cameo.pal", "anim.pal"} | {f"unit{t}.pal" for t in THEATERS}
        optional = set()
        for name in self.images - self.seqs:
            old = A[name].get("Image", name)
            if A[name].get("Voxel", "no").lower() == "yes":
                need |= {old + ".vxl", old + ".hva"}
                optional |= {old + part + ext for part in VOXEL_PARTS[1:]
                             for ext in (".vxl", ".hva")}
            elif name in self.techno_images:
                need.add(old + ".shp")
            else:
                optional.add(old + ".shp")
        for n in self.technos:
            art = A[self.c("a", self.T["r"][n].get("Image", n))]
            # SHP cameos are only needed for what goes on the sidebar
            if n not in UNITS and n not in VEHICLES:
                continue
            for p in ("Cameo", "AltCameo"):
                if art.get(p):
                    optional.add(art[p] + ".shp")
        return need, optional

    def samples(self):
        out = set()
        for n in self.sel["s"]:
            for x in self.T["s"][n].get("Sounds", "").replace(",", " ").split():
                out.add(x.lstrip("$!").lower())
        return out


def load_source():
    def rd(n):
        return open(os.path.join(paths.ABC_SRC, n), encoding="utf-8").read()
    return ini_parse(rd("ABCRULE.INI")), ini_parse(rd("ABCYS.INI")), ini_parse(rd("SOUNDMD.INI"))


# ---------------------------------------------------------------------------
# stage 1: snapshot the ABC data we need
# ---------------------------------------------------------------------------

def _mix_entries(d):
    from Crypto.Cipher import Blowfish
    flags, = struct.unpack_from("<I", d)
    if flags & 0xFFFF:
        h, start = d, 0
    elif flags & 0x20000:
        # public Westwood key (OpenRA BlowfishKeyProvider)
        mod = int.from_bytes(base64.b64decode(
            "AihRvNoIbTn85FZRYNZRcT+i6KpU+maCsEqr3Q5q+LDB5tH7Tz2qQ38V")[2:], "big")
        key = b"".join(pow(int.from_bytes(d[i:i + 40], "little"), 65537, mod)
                       .to_bytes(40, "little")[:39] for i in (4, 44))[:56]
        bf = Blowfish.new(key, Blowfish.MODE_ECB)
        n = struct.unpack_from("<H", bf.decrypt(d[84:92]))[0]
        size = ((6 + n * 12 + 7) // 8) * 8
        h, start = bf.decrypt(d[84:84 + size]), 84 + size
    else:
        h, start = d[4:], 4
    n, _ = struct.unpack_from("<HI", h)
    if not flags & 0x20000 or flags & 0xFFFF:
        start += 6 + n * 12
    return start, [struct.unpack_from("<III", h, 6 + i * 12) for i in range(n)]


class Archives:
    NESTED = ["localmd.mix", "local.mix", "conqmd.mix", "conquer.mix", "genermd.mix",
              "generic.mix", "cachemd.mix", "cache.mix", "cameomd.mix", "cameo.mix",
              "ntrlmd.mix", "neutral.mix", "isogenmd.mix", "isogen.mix",
              "audiomd.mix", "audio.mix"]

    def __init__(self, root, top):
        self.root, self.arc = root, []
        for fn in top:
            p = os.path.join(root, fn)
            if os.path.exists(p):
                self._add(open(p, "rb").read(), fn, 0)

    def _add(self, data, label, depth):
        try:
            start, entries = _mix_entries(data)
        except Exception:
            return
        tab = {i: (start + o, n) for i, o, n in entries if start + o + n <= len(data)}
        self.arc.append((label, data, tab))
        if depth < 2:
            for nm in self.NESTED:
                if mix_id(nm) in tab:
                    o, n = tab[mix_id(nm)]
                    self._add(data[o:o + n], f"{label}/{nm}", depth + 1)

    def get(self, name):
        p = os.path.join(self.root, name)
        if os.path.isfile(p):
            return open(p, "rb").read()
        h = mix_id(name)
        for _, blob, tab in self.arc:
            if h in tab:
                o, n = tab[h]
                return blob[o:o + n]
        return None


def _pcm_wav(raw, rate, flags, chunk):
    ch = 2 if flags & 1 else 1
    if flags & 8:        # IMA ADPCM blocks without a RIFF header
        spb = ((chunk - ch * 4) * 2 // ch) + 1
        fmt = struct.pack("<HHIIHHHH", 0x11, ch, rate, rate * chunk // spb, chunk, 4, 2, spb)
        body = (b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"fact" +
                struct.pack("<II", 4, len(raw) // chunk * spb))
    else:
        bits = 16 if flags & 4 else 8
        al = ch * bits // 8
        fmt = struct.pack("<HHIIHH", 1, ch, rate, rate * al, al, bits)
        body = b"fmt " + struct.pack("<I", 16) + fmt
    body += b"data" + struct.pack("<I", len(raw)) + raw + (b"\0" if len(raw) % 2 else b"")
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


def extract(abc_game):
    src = Archives(abc_game, ["expandmd02.mix", "expandmd01.mix", "ra2md.mix",
                              "ra2.mix", "langmd.mix", "language.mix"])
    os.makedirs(os.path.join(paths.ABC_SRC, "assets"), exist_ok=True)
    for n in ("ABCRULE.INI", "ABCYS.INI", "SOUNDMD.INI"):
        b = src.get(n)
        assert b, n
        with open(os.path.join(paths.ABC_SRC, n), "w", encoding="utf-8", newline="") as fh:
            fh.write(b.decode("gb18030", errors="replace"))
    cl = Closure(*load_source())
    assert not cl.missing, cl.missing
    need, optional = cl.asset_names()
    got = {}
    for n in sorted(need | optional):
        b = src.get(n)
        if b is None:
            assert n not in need, "missing required asset " + n
            continue
        got[n.lower()] = b
    idx, bag = src.get("audio.idx"), src.get("audio.bag")
    table = {}
    for i in range(struct.unpack_from("<I", idx, 8)[0]):
        nm, off, size, rate, fl, chunk = struct.unpack_from("<16s5I", idx, 12 + i * 36)
        table[nm.split(b"\0")[0].decode("ascii").lower()] = (off, size, rate, fl, chunk)
    for s in sorted(cl.samples()):
        b = src.get(s + ".wav")
        if b is None and s in table:
            off, size, rate, fl, chunk = table[s]
            b = _pcm_wav(bag[off:off + size], rate, fl, chunk)
        if b is not None:
            got[s + ".wav"] = b
    for n, b in got.items():
        with open(os.path.join(paths.ABC_SRC, "assets", n), "wb") as fh:
            fh.write(b)
    from csftool import Csf
    c = Csf(os.path.join(abc_game, "ra2md.csf"))
    manifest = {
        "units": list(UNITS),
        "closure": {d: sorted(v) for d, v in cl.sel.items()},
        "assets": {n: hashlib.sha256(b).hexdigest() for n, b in sorted(got.items())},
        "source_names": {u: c.get(cl.T["r"][u]["UIName"]) or
                         c.get(cl.T["r"][u]["UIName"].upper()) for u in UNITS},
    }
    with open(os.path.join(paths.ABC_SRC, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(f"抽取完成：规则 {len(cl.sel['r'])} 段 / 美术 {len(cl.sel['a'])} 段 / "
          f"音效 {len(cl.sel['s'])} 段 / 资源 {len(got)} 个 -> {paths.ABC_SRC}")


# ---------------------------------------------------------------------------
# stage 2: produce the MO-side content (called by build_mod.py)
# ---------------------------------------------------------------------------

def _pcx(w, h, pixels, palette_rgb):
    from PIL import Image
    im = Image.frombytes("P", (w, h), pixels)
    im.putpalette(palette_rgb)
    import io
    buf = io.BytesIO()
    im.save(buf, format="PCX")
    return buf.getvalue()


def _invert_pal(pal):
    """Colour-invert a 6-bit RA2 palette. Index 0 (transparent) and the
    near-black entries stay: ABC bakes the infantry shadow and outlines into
    the body frames with those (12/61-63 in unittem), and inverting them
    would stand the unit on a white shadow."""
    out = bytearray(pal[:3])
    for i in range(3, len(pal), 3):
        rgb = pal[i:i + 3]
        out += rgb if max(rgb) <= 4 else bytes(63 - (x & 63) for x in rgb)
    return bytes(out)


def _satori_cameo(rgb):
    """Koishi's portrait recoloured toward Satori (lavender-pink hair, blue
    top), her third eye top-left, and a 觉 label band. 60x48 RGB in and out."""
    import colorsys
    from PIL import Image, ImageDraw, ImageFont
    im = rgb.copy()
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            deg = h * 360
            if s > 0.12 and 60 <= deg < 170:          # green hair / skirt
                h, s, v = 318 / 360, max(s, 0.5), min(1, v * 1.08)
            elif s > 0.25 and 30 <= deg < 60:         # yellow blouse
                h = 222 / 360
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            px[x, y] = (int(r * 255), int(g * 255), int(b * 255))
    K = 4
    big = im.resize((60 * K, 48 * K), Image.LANCZOS)
    d = ImageDraw.Draw(big, "RGBA")
    cx, cy = 9 * K, 8 * K                              # the third eye
    for a, b in ((-3, 3), (-1, 5)):
        d.line([(cx + a * K, cy + 2 * K), (cx + b * K * 2, cy + 9 * K)],
               fill=(230, 90, 150, 255), width=K)
    d.ellipse([cx - 6 * K, cy - 4 * K, cx + 6 * K, cy + 4 * K],
              fill=(250, 235, 240, 255), outline=(200, 40, 110, 255), width=K)
    d.ellipse([cx - 3 * K, cy - 3 * K, cx + 3 * K, cy + 3 * K], fill=(210, 30, 80, 255))
    d.ellipse([cx - 1.2 * K, cy - 1.2 * K, cx + 1.2 * K, cy + 1.2 * K], fill=(40, 0, 20, 255))
    top = 48 * K - 12 * K                              # label band over the old 恋
    d.rectangle([0, top, 60 * K - 1, 48 * K - 1], fill=(30, 12, 34, 225))
    d.rectangle([0, top, 60 * K - 1, top + K], fill=(236, 120, 180, 255))
    f = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 10 * K)
    l, t, r, b = d.textbbox((0, 0), "觉", font=f)
    d.text(((60 * K - (r - l)) / 2 - l, top + K + (11 * K - (b - t)) / 2 - t), "觉",
           font=f, fill=(255, 255, 255))
    return big.resize((60, 48), Image.LANCZOS)


def _pcx_rgb(im):
    import io
    from PIL import Image
    buf = io.BytesIO()
    im.convert("P", palette=Image.ADAPTIVE, colors=256).save(buf, format="PCX")
    return buf.getvalue()


def build(owner, existing_sections, stock):
    """Return everything build_mod.py needs to merge.

    owner              the 12-country Owner= string
    existing_sections  upper-cased section names already in rulesmo/artmo,
                       to prove the namespace is collision-free
    stock              name -> dict of MO's own rules (for Satori's weapons)
    """
    R, A, S = load_source()
    cl = Closure(R, A, S)
    assert not cl.missing, cl.missing

    def asset(n):
        p = os.path.join(paths.ABC_SRC, "assets", n.lower())
        return open(p, "rb").read() if os.path.exists(p) else None

    rmap = {n: type_id("ABC_", n) for n in cl.sel["r"]}
    amap = {n: f"ABP{i:05}" for i, n in enumerate(sorted(cl.sel["a"]), 1)}
    smap = {n: type_id("ABCS_", n) for n in cl.sel["s"]}
    maps = {"r": rmap, "a": amap, "s": smap}
    for d, m in maps.items():
        assert all(len(v) <= 24 for v in m.values()), d
        assert len({v.upper() for v in m.values()}) == len(m), d
        clash = {v.upper() for v in m.values()} & existing_sections
        assert not clash, f"namespace collision: {sorted(clash)[:5]}"

    files = {}
    notes = []
    for t in THEATERS:
        files[f"abunit{t}.pal"] = asset(f"unit{t}.pal")
    files["abanim.pal"] = asset("anim.pal")
    for t in THEATERS:
        files[f"{SATORI_PAL}{t}.pal"] = _invert_pal(asset(f"unit{t}.pal"))
    assert all(files.values())

    for name in sorted(cl.images - cl.seqs):
        old = A[name].get("Image", name)
        if A[name].get("Voxel", "no").lower() == "yes":
            for part in VOXEL_PARTS:
                for ext in (".vxl", ".hva"):
                    b = asset(old + part + ext)
                    assert b or part, "missing voxel " + old + ext
                    if b:
                        files[amap[name].lower() + part + ext] = b
            continue
        b = asset(old + ".shp")
        if b is None:
            assert name not in cl.techno_images, "missing unit sprite " + name
            # trailer / particle carriers that have no shape in the source
            b = encode_shp(1, 1, [0], frames=2)
            notes.append(name)
        files[amap[name].lower() + ".shp"] = b

    # --- cameos: source SHP cameo + ABC's cameo.pal -> MO-style PCX ----------
    # index 0 is "transparent" in an SHP but PCX has no transparency: the
    # corners would show up as the palette's pure blue, so paint it black
    cam_pal = b"\0\0\0" + bytes(min(255, x * 4) for x in asset("cameo.pal"))[3:]
    cameo_pcx = {}
    order = list(UNITS) + list(VEHICLES)
    for i, u in enumerate(order):
        art = A[cl.c("a", R[u].get("Image", u))]
        main = art.get("Cameo")
        alt = art.get("AltCameo") or main
        assert main and asset(main + ".shp"), f"{u}: no source cameo"
        for tag, src in (("n", main), ("e", alt)):
            b = asset(src + ".shp") or asset(main + ".shp")
            w, h, px = shp_frame(b)
            assert (w, h) == (60, 48), (u, w, h)
            if u == SATORI:
                from PIL import Image
                im = Image.frombytes("P", (w, h), px)
                im.putpalette(cam_pal)
                cameo_pcx[f"abc{i:02}{tag}.pcx"] = _pcx_rgb(_satori_cameo(im.convert("RGB")))
            else:
                cameo_pcx[f"abc{i:02}{tag}.pcx"] = _pcx(w, h, px, cam_pal)
    cameo_of = {u: (f"abc{i:02}n.pcx", f"abc{i:02}e.pcx") for i, u in enumerate(order)}

    # --- sounds ---------------------------------------------------------------
    samples = {}
    sounds = {}
    for n in sorted(cl.sel["s"]):
        sec = dict(S[n])
        out = []
        for x in sec.get("Sounds", "").replace(",", " ").split():
            old = x.lstrip("$!").lower()
            if old not in samples:
                b = asset(old + ".wav")
                if b is None:
                    continue
                samples[old] = f"ABS{len(samples) + 1:05}"
                files[samples[old].lower() + ".wav"] = b
            out.append(("$" if x.startswith("$") else "") + samples[old])
        sec["Sounds"] = " ".join(out)
        sounds[smap[n]] = sec

    # --- rules / art sections -----------------------------------------------
    def remap(d, name, sec):
        out = {}
        for k, v in sec.items():
            kl = k.lower()
            tgt = ref_domain(kl) or ("a" if (d == "a" and kl == "sequence") else None)
            if tgt:
                v = ",".join(maps[tgt].get(cl.c(tgt, x), x) for x in tokens(v))
            if kl == "image":
                v = amap.get(cl.c("a", v), v) if d == "r" else amap[name]
            out[k] = v
        return out

    rules = collections.OrderedDict()
    strings = {}
    for n in sorted(cl.sel["r"]):
        sec = remap("r", n, R[n])
        if n in cl.technos:
            sec["Image"] = amap[cl.c("a", R[n].get("Image", n))]
            sec["UIName"] = f"NAME:{rmap[n]}"
            sec["Owner"] = owner
            for k in list(sec):
                if k.startswith(GATES):
                    del sec[k]
            sec["AIBuildThis"] = "no"
            sec["AllowedToStartInMultiplayer"] = "no"
            if n in UNITS:
                sec.update(Prerequisite=PREREQ, TechLevel="10", IFVMode="0",
                           Cloneable="no")
                if sec.get("BuildLimit") == "-1":
                    sec["BuildLimit"] = "1"
                strings[f"NAME:{rmap[n]}"] = UNITS[n]
            elif n in VEHICLES:
                sec.update(Prerequisite=VEHICLE_PREREQ, TechLevel="10", IFVMode="0")
                strings[f"NAME:{rmap[n]}"] = VEHICLES[n]
            else:
                # dragged in as a dependency (e.g. the Shanghai doll): exists
                # in the game, never on any sidebar
                sec["TechLevel"] = "-1"
                sec.pop("Prerequisite", None)
                strings[f"NAME:{rmap[n]}"] = n.title()
            # MO's numbers run higher than ABC's across the board; units with
            # user-given stats take those instead
            sec["Strength"] = str(int(sec["Strength"]) * STRENGTH_MUL)
            sec.update(OVERRIDES.get(n, {}))
            if "RadarInvisble" in sec:       # source typo
                sec["RadarInvisible"] = sec.pop("RadarInvisble")
        if cl.kinds.get(n.lower()) == "Particles" and "Image" in sec:
            sec["Palette"] = "abanim.pal"
        for k, v in list(sec.items()):
            if not v.isascii():              # e.g. Chinese Name= comments
                sec[k] = rmap[n] if k == "Name" else v.encode("ascii", "ignore").decode()
        rules[rmap[n]] = sec

    art = collections.OrderedDict()
    for n in sorted(cl.sel["a"]):
        sec = remap("a", n, A[n])
        sec.pop("Cameo", None)
        sec.pop("AltCameo", None)
        if n in cl.techno_images:
            if sec.get("Voxel", "no").lower() != "yes":   # voxels use the voxel palette
                sec["Palette"] = "abunit"    # -> abunit<theater>.pal, like MO's YUNRU
        elif n not in cl.seqs:
            sec["CustomPalette"] = "abanim.pal"
        art[amap[n]] = sec
    for u in order:
        if u == SATORI:
            continue
        a = amap[cl.c("a", R[u].get("Image", u))]
        art[a]["CameoPCX"], art[a]["AltCameoPCX"] = cameo_of[u]

    # --- Satori: own art entry (copied sprite, inverted palette) + medic kit
    koishi = cl.c("a", R[SATORI].get("Image", SATORI))
    sat = dict(art[amap[koishi]])
    sat.update(Palette=SATORI_PAL, CameoPCX=cameo_of[SATORI][0],
               AltCameoPCX=cameo_of[SATORI][1])
    art[SATORI_ART] = sat
    files[SATORI_ART.lower() + ".shp"] = files[amap[koishi].lower() + ".shp"]
    unit = rules[rmap[SATORI]]
    unit["Image"] = SATORI_ART
    for key, (new, old) in SATORI_WEAPONS.items():
        w = dict(stock(old))
        assert w, f"MO weapon {old} not found"
        w["ROF"] = str(max(1, round(int(w["ROF"]) / SATORI_ROF_DIV)))
        w["Range"] = SATORI_RANGE
        rules[new] = w
        unit[key] = new
    unit.update(SATORI_KEYS)
    for k in SATORI_NO_KEYS:
        unit.pop(k, None)
    for n in [SATORI_ART] + [v[0] for v in SATORI_WEAPONS.values()]:
        assert n.upper() not in existing_sections and len(n) <= 24, n

    for sec in list(art.values()) + list(sounds.values()):
        for k, v in list(sec.items()):
            if not v.isascii():
                sec[k] = v.encode("ascii", "ignore").decode()

    regs = {k: sorted(rmap[n] for n in cl.sel["r"] if cl.kinds.get(n.lower()) == k)
            for k in REGS if k != "Animations"}
    regs["Animations"] = sorted(amap[n] for n in (cl.anims | cl.sprite_images)
                                if n not in cl.techno_images and n in amap)

    # every art/rules/sound reference inside the block must resolve
    known = {"r": set(rules), "a": set(art), "s": set(smap.values())}
    for d, block in (("r", rules), ("a", art)):
        for sn, sec in block.items():
            for k, v in sec.items():
                kl = k.lower()
                tgt = ref_domain(kl)
                if tgt:
                    for x in tokens(v):
                        assert x in known[tgt] or x.lower() == "none" or \
                            not x.upper().startswith(("ABC", "ABP")), (sn, k, x)
                        assert len(x) <= 24, (sn, k, x)

    return {
        "rules": rules, "art": art, "sounds": sounds, "registrations": regs,
        "strings": strings, "mix": write_mix(files), "mix_files": sorted(files),
        "cameos": cameo_pcx, "units": [rmap[u] for u in UNITS],
        "vehicles": [rmap[u] for u in VEHICLES],
        "unit_images": {rmap[u]: rules[rmap[u]]["Image"] for u in UNITS},
        "invisible_carriers": notes,
    }


if __name__ == "__main__":
    print(__doc__)
