"""Where everything lives. Every tool calls configure() once; the values are
module globals, read as paths.GAME, paths.PRISTINE, ...

  <game>                    your Mental Omega 3.3.6 installation
  <work>/pristine/          stock files read out of that installation (mixes,
                            plus the one loose challenge map Boris comes from)
  <work>/original/          every game file the patch replaced, as it was, at
                            its game-relative path; manifest.json lists every
                            file the patch wrote and whether it replaced or added
                            it, which is what --restore undoes
  <work>/output/            what the patch writes, laid out like the game folder
  <work>/third_party/       optional, snapshotted with --qier:
      phobos/               Phobos.dll + .pdb + SyringeEx (the UI features)
      qier_maps/            the 12 skirmish maps
  <work>/abc_source/        optional, snapshotted with --abc: the Touhou port

--game and --work are remembered in <repo>/local.json (git-ignored), so later
runs need no arguments.
"""
import json
import os
import sys

# The tools print Chinese. Keep a console that can show it (cp936 etc.);
# switch anything that cannot (cp1252 pipes) to UTF-8 instead of crashing.
for _s in (sys.stdout, sys.stderr):
    try:
        "中".encode(_s.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
CAMEOS = os.path.join(REPO, "cameos")
LOCAL = os.path.join(REPO, "local.json")

GAME = WORK = PRISTINE = ORIGINAL = OUTPUT = THIRD = None
ABC_SRC = QIER_SNAP = PHOBOS_DIR = SYRINGE_EX = None
MANIFEST = None


def add_args(ap):
    ap.add_argument("--game", default=None,
                    help="your Mental Omega 3.3.6 folder (remembered after the first run)")
    ap.add_argument("--work", default=None,
                    help="scratch + backup folder (default: <repo>/work; remembered)")


def configure(args, remember=False):
    global GAME, WORK, PRISTINE, ORIGINAL, OUTPUT, THIRD
    global ABC_SRC, QIER_SNAP, PHOBOS_DIR, SYRINGE_EX, MANIFEST
    saved = {}
    if os.path.isfile(LOCAL):
        with open(LOCAL, encoding="utf-8") as fh:
            saved = json.load(fh)
    game = getattr(args, "game", None) or saved.get("game")
    work = getattr(args, "work", None) or saved.get("work") or os.path.join(REPO, "work")
    if not game:
        raise SystemExit('first run: tell me where the game is, e.g. '
                         '--game "D:/Games/Mental Omega"')
    GAME = os.path.abspath(game)
    WORK = os.path.abspath(work)
    if not os.path.isfile(os.path.join(GAME, "expandmo99.mix")):
        raise SystemExit("not a Mental Omega 3.3.6 folder (no expandmo99.mix): " + GAME)
    PRISTINE = os.path.join(WORK, "pristine")
    ORIGINAL = os.path.join(WORK, "original")
    OUTPUT = os.path.join(WORK, "output")
    THIRD = os.path.join(WORK, "third_party")
    ABC_SRC = os.path.join(WORK, "abc_source")
    QIER_SNAP = os.path.join(THIRD, "qier_maps")
    PHOBOS_DIR = os.path.join(THIRD, "phobos")
    SYRINGE_EX = os.path.join(PHOBOS_DIR, "SyringeEx-0.7.2.0.exe")
    MANIFEST = os.path.join(ORIGINAL, "manifest.json")
    for d in (PRISTINE, ORIGINAL, OUTPUT):
        os.makedirs(d, exist_ok=True)
    if remember and (saved.get("game") != GAME or saved.get("work") != WORK):
        with open(LOCAL, "w", encoding="utf-8") as fh:
            json.dump({"game": GAME, "work": WORK}, fh, ensure_ascii=False, indent=1)


def have_abc():
    return os.path.isfile(os.path.join(ABC_SRC, "manifest.json"))


def have_qier_maps():
    return os.path.isfile(os.path.join(QIER_SNAP, "entries.json"))


def have_phobos():
    return all(os.path.isfile(os.path.join(PHOBOS_DIR, f))
               for f in ("Phobos.dll", "Phobos.pdb")) and os.path.isfile(SYRINGE_EX)
