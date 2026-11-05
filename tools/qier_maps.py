"""Twelve skirmish maps from the "企鹅的心灵终结 v1.1" (Mental Omega QiEr) pack.

Four reworked classics and eight "special event" maps. They use Mental
Omega's own units only - none of the QiEr pack's new ones - so they work on
plain MO rules. Two of them (决战山巅 盟军/苏军) [#include] SP_LIBRA.ini, their
own Libra-boss content, which references nothing but MO types either.

Left out on purpose: eastwindevalleycover (东风谷-改). It [#include]s the
QiEr pack's whole BalanceAdjustments.ini (27 new units, 104 rebalanced stock
entries) while its description says "no special elements" - the user did not
want it.

  build_mod.py --qier "<pack>"    one-off: snapshot maps, previews, SP_LIBRA.ini
                                  and their MentalOmegaMaps.ini entries into
                                  <work>/third_party/qier_maps/, and the pack's
                                  Phobos + SyringeEx into <work>/third_party/phobos/
  build_mod.py                    calls build() on every run (skipped if absent)
"""
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths                                             # noqa: E402

FOLDER = "qier_maps"                       # MapsMO\qier_maps\, as in the QiEr pack
MAPS = [
    "bowtiecanyoncover", "canyonfrostcover", "pacificrimcover",          # [常规]…-改
    "dazzlingcrownoftechnology", "finalshowdownonthepeaksu", "quinarybarrage2",
    "supertanki", "DangerousFortress", "finalshowdownonthepeakmeng",
    "epsanimalworld", "thecourtyardwhereffdescends", "finalshowdownonthepeaktech",
]
EXCLUDED = ["eastwindevalleycover"]
EXTRA_FILES = ["SP_LIBRA.ini"]             # game root; included by the two 决战山巅 maps


def entry_name(m):
    return "MapsMO\\" + FOLDER + "\\" + m


# Phobos 0.5.0.0-alpha2 (GPL-3.0) and SyringeEx 0.7.2.0 as the pack ships them;
# the pack's Syringe.exe *is* SyringeEx.
PHOBOS_FROM = {"Phobos.dll": "Phobos.dll", "Phobos.pdb": "Phobos.pdb",
               "SyringeEx-0.7.2.0.exe": "Syringe.exe",
               "Syringe.LICENSE.txt": "Syringe.LICENSE.txt"}


def extract(qier):
    SNAP = paths.QIER_SNAP
    os.makedirs(SNAP, exist_ok=True)
    src_dir = os.path.join(qier, "MapsMO", FOLDER)
    for m in MAPS:
        for ext in (".map", ".png"):
            shutil.copy2(os.path.join(src_dir, m + ext), os.path.join(SNAP, m + ext))
    for f in EXTRA_FILES:
        shutil.copy2(os.path.join(qier, f), os.path.join(SNAP, f))
    lines = open(os.path.join(qier, "INI", "MentalOmegaMaps.ini"), "rb").read() \
        .decode("utf-8-sig").split("\r\n")
    entries, cur = {}, None
    wanted = {entry_name(m).lower(): m for m in MAPS}
    for line in lines:
        s = line.strip()
        if s.startswith("[") and "]" in s:
            cur = wanted.get(s[1:s.index("]")].strip().lower())
            if cur:
                entries[cur] = []
            continue
        if cur and "=" in s and not s.startswith(";"):
            k, v = s.split("=", 1)
            entries[cur].append([k.strip(), v.strip()])
    assert set(entries) == set(MAPS), sorted(set(MAPS) - set(entries))
    with open(os.path.join(SNAP, "entries.json"), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)
    print(f"快照完成：{len(MAPS)} 张图（含预览）+ {', '.join(EXTRA_FILES)} + 地图列表条目 -> {SNAP}")
    os.makedirs(paths.PHOBOS_DIR, exist_ok=True)
    for dst, src in PHOBOS_FROM.items():
        shutil.copy2(os.path.join(qier, src), os.path.join(paths.PHOBOS_DIR, dst))
    assert b"SyringeEx" in open(paths.SYRINGE_EX, "rb").read(), "the pack's Syringe.exe is not SyringeEx"
    print(f"快照完成：Phobos + SyringeEx -> {paths.PHOBOS_DIR}")


def build(maps_ini):
    """Register the maps in MentalOmegaMaps.ini (moini Ini, utf-8-sig) and
    return {destination relative path: source path} to deploy."""
    SNAP = paths.QIER_SNAP
    entries = json.load(open(os.path.join(SNAP, "entries.json"), encoding="utf-8"))
    existing = {v.lower() for v in maps_ini.list_values("MultiMaps")}
    names = [entry_name(m) for m in MAPS]
    assert not ({n.lower() for n in names} & existing), "already registered"
    maps_ini.append_to_list("MultiMaps", names)
    for m in MAPS:
        assert not maps_ini.has_section(entry_name(m)), m
        maps_ini.append_section(entry_name(m), [tuple(kv) for kv in entries[m]])
    files = {}
    for m in MAPS:
        for ext in (".map", ".png"):
            files[os.path.join("MapsMO", FOLDER, m + ext)] = os.path.join(SNAP, m + ext)
    for f in EXTRA_FILES:
        files[f] = os.path.join(SNAP, f)
    return files


def includes(map_path):
    """[#include] targets of a map file."""
    t = open(map_path, "rb").read().decode("latin-1")
    m = re.search(r"^\[#include\]\s*$(.*?)(?=^\[|\Z)", t, re.M | re.S)
    return [l.split("=", 1)[1].strip() for l in (m.group(1).splitlines() if m else [])
            if "=" in l and not l.strip().startswith(";")]


if __name__ == "__main__":
    print(__doc__)
