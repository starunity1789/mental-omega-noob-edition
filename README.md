# Mental Omega — Noob Edition

A single-player quality-of-life patch for **Mental Omega 3.3.6** (a fan-made
expansion for *Command & Conquer: Red Alert 2 — Yuri's Revenge*).

It unlocks the co-op missions for offline play, adds six always-available
support powers, and lets you deploy a tech MCV that opens any faction's full
tech tree — while leaving ordinary skirmish and campaign play **provably
untouched**.

**中文说明见 [README.zh-CN.md](README.zh-CN.md)。**

![support power cameos](docs/cameos.png)

---

## ⚠️ Offline use only — do not take this online

**This build is not for multiplayer.** Do not host it, do not join CnCNet or
LAN games with it, do not play it against other people.

It changes `rulesmo.ini`, which means your game no longer matches anyone
else's. Using it online will desync the match, ruin the game for everyone in
it, and is simply cheating.

It exists for two kinds of players:

- people who keep getting stuck on a campaign mission and just want to see the
  rest of the story;
- people who have nobody to play the co-op missions with, and until now could
  not play them at all.

If you have friends to play with, play the real thing. It is better.

---

## What it changes

### 1. Co-op missions, playable offline

All 36 co-op maps now appear under **Skirmish → Game Mode → Co-Op
(Casual / Normal / Brutal)**. No CnCNet, no lobby, no second human.

Mental Omega locks them in three separate places; all three are cleared:

| Where | Flag |
|---|---|
| `MentalOmegaMaps.ini`, the three Co-Op mode sections | `HumanPlayersOnly`, `MultiplayerOnly` |
| `MentalOmegaMaps.ini`, each of the 36 per-map entries | `MultiplayerOnly` |
| The 36 `.map` files, `[Basic]` | `MultiplayerOnly` |

The maps keep `MinPlayer=2`, so **put an AI ally in slot 2**. That is
deliberate: several missions' win/lose triggers reference the second house, and
the client builds the scripted enemy AI from each map's own `EnemyHouse0/1`
entries, so the mission plays out properly.

> These missions cannot be moved onto the Campaign screen. Co-op maps have no
> `[Houses]` section at all — every house is created from the lobby's
> `spawn.ini`. The Campaign screen uses the single-house launch path, so the
> houses would simply never exist and the trigger chain would break. Skirmish
> uses the same multiplayer house logic the lobby does, which is why it works.

### 2. Six support powers, always available

Built on Ares' `SW.AlwaysGranted`, so they need no building, survive a power
outage, and stay available even with *Superweapons: Off*.

| Power | Delivers |
|---|---|
| 传送：长剑毁灭装甲 | Shin Tsurugi Decimator |
| 传送：混合塔 | Hybrid Tower |
| 传送：盟军科技基地车 | Allied Tech MCV |
| 传送：苏军科技基地车 | Soviet Tech MCV |
| 传送：厄普西隆科技基地车 | Epsilon Tech MCV |
| 传送：焚风科技基地车 | Foehn Tech MCV |

`SW.AllowAI=no` — the AI never gets any of them.

### 3. Hybrid Tower tuning

| Key | Stock | Noob |
|---|---|---|
| `Power` / `Powered` | -150 / yes | **0 / no** (no drain, works unpowered) |
| `Sight` | 8 | **16** |
| Weapon range | 14 / 15 | **21 / 22.5** (stock +50%) |
| `Strength` | 1050 | **3333** |
| `SelfHealing` | — | **yes** |
| Anti-air | none | **yes** |

Anti-air is done with a new projectile, `InvisibleHighAA` — a copy of
`InvisibleHigh` with `AA=yes`. The stock projectile is shared by 90 weapons and
is never touched; `HybridBolt`/`E`/`Support` are used by the Hybrid Tower and
nothing else in the entire mod, so the swap has no side effects.

### 4. Four tech MCVs

A support power delivers a tech MCV; deploy it and that faction's **entire**
tech tree becomes buildable — you construct and pay for everything normally,
nothing is gifted.

Mental Omega gates construction with four independent tags, all verified
against `Ares.dll`:

```
buildable countries = Owner ∩ RequiredHouses ∩ FactoryOwners − ForbiddenHouses
```

Every registered type is classified by that formula:

| Group | Count | Treatment | Effect on normal play |
|---|---:|---|---|
| Effective owners already cover a whole faction | 188 | open to all 12 countries | **none** |
| Sub-faction exclusive | 94 | **cloned** into new `SU*` entries; the originals are not touched | **none** |
| Stolen-tech units behind the beacon | 10 (+2 partners) | cloned; gated on the beacon | **none** |
| Props, spawned objects, projectiles | rest | untouched | — |

The clones require the tech Construction Yard, so a normal player — who only
ever has their own stock yard — can never see them. Euro Alliance's Cavalier
stays Euro Alliance's.

### 5. Far Star Support Beacon

A new building any tech Construction Yard can put up. It is a rebuild of Mental
Omega's *Blackout Research Station* prop — the donor art has no `Buildup=`, so
it appears without a construction animation. Cosmetic only.

It does two things.

**Carries the Far Star Knights Aid support power** — built from MO's own
`PaladinAidSpecial`, so it behaves like a stock power:

| | |
|---|---|
| Delivers | 2x Prism Tank, 2x Abrams, 2x Blizzard, 2x Paladin Hunter, 1x Repair Drone |
| Cost | 8500 |
| Recharge | 15 seconds |
| Power | goes offline with the grid |

**Unlocks ten stolen-tech units at any faction's war factory**: Quickshifter,
Future Tank Alpha, Grumble AA, Apocalypse, Iron Dragon, Scavenger, Worm Queen,
Phantom MLRS, Seitaad Ballista, Ram.

Those ten are normally locked behind a spy infiltration, and the gate does not
live in `rulesmo.ini` at all — it is in `INI/Game Options/Stolen Tech.ini`,
which the client merges into the map at launch and which therefore *overrides*
the rules. Editing that file would hand every player the ten units without a
spy, so the patch clones them instead: `SU*` copies whose prerequisite is
`FACTORY` plus the beacon. The stock ten are left byte for byte alone and
`Stolen Tech.ini` is never touched, which keeps the regression proof valid.

The two units that transform (Future Tank Alpha, Grumble) get their partners
cloned too, so a deployed clone never hands back a stock unit the player has no
tech for.

---

## Install

You need your own legal copy of **Mental Omega 3.3.6**. This repository ships
**no** Mental Omega content — the patcher reads the pristine rules out of your
installation's `expandmo99.mix` and writes the patched result back.

Requires Python 3.8+ (`pip install pillow` only if you want to regenerate the
cameo icons; the six PCX files are already included).

```bash
git clone https://github.com/starunity1789-bot/mental-omega-noob-edition.git
cd mental-omega-noob-edition
python tools/build_mod.py --game "D:/Games/Mental Omega"
```

The first run snapshots every file it is about to touch into `work/backup/`.

```bash
# build without touching the game, for inspection
python tools/build_mod.py --game "..." --dry

# prove the patch changes nothing for a normal player
python tools/validate.py --game "..."

# undo everything, byte for byte
python tools/build_mod.py --game "..." --restore
```

Tool output is in Chinese, since that is who this is for.

---

## How "no effect on normal play" is verified

`tools/validate.py` runs three passes:

- **Structural** — every registered type is unique, every referenced ID
  resolves, every clone's convert/deploy links point at clones rather than
  stock partners, every cameo is a valid 60×48 8-bit PCX.
- **Regression** — for each of the 12 countries, it computes the complete set
  of everything that country can build, before and after the patch, and
  requires the two sets to be **identical item for item**. This is the machine
  proof that ordinary skirmish and campaign play are unchanged.
- **Unlock coverage** — with a foreign tech Construction Yard, **100 %** of
  that faction's exclusive buildable content becomes reachable.
- **Beacon gate** — the ten stolen-tech clones are unbuildable without the
  beacon standing and all ten are buildable with it, and the ten stock entries
  are compared key by key against pristine to prove they never moved.

It was also checked in game against Ares' own parser log, same map and seed,
stock rules versus patched:

| Ares log | Stock | Noob |
|---|---:|---:|
| `Failed to parse` | 0 | 0 |
| `Abandoning production of` | 0 | 0 |
| `[Developer error]` | 1 | 1 |
| `[Developer warning]` | 1 | 1 |
| `[Developer fatal]` | 586 | 586 |
| `[Developer notice]` | 30 | 30 |

(The one warning and the notices are Mental Omega's own — stock MO already
ships 1156 `BuildingTypes`, over the 512 Ares warns about.)

---

## Copyright

**Command & Conquer: Red Alert 2 — Yuri's Revenge is © Electronic Arts.**

**Mental Omega is the work of Speeder and the Mentalmeisters**, powered by Ares
(AlexB) and the CnCNet team. All Mental Omega assets, rules, maps, artwork,
text and balance design belong to them.

This repository claims none of it. It contains only patch scripts, six cameo
icons drawn for the new support powers, and documentation. Every byte of game
content is read from, and written back to, your own installation.

Mental Omega's own readme asks that it not be re-uploaded without permission,
which is exactly why this is a patcher and not a repack. **Get the game from
[mentalomega.com](https://mentalomega.com) only.**

This project is unofficial, is not endorsed by Electronic Arts or by the
Mental Omega team, and is not supported by either. If the Mental Omega team
would like it taken down, it will be.

## Acknowledgements

- Speeder and the Mentalmeisters — Mental Omega
- AlexB — Ares
- The CnCNet team — client and multiplayer infrastructure
