"""Mental Omega build-tree model: ownership, prerequisites, faction roots.

The whole mod rests on one observation: MO gates *buildings* by
`Prerequisite=<faction Construction Yard>` but gates *units* by `Owner=`
(a country whitelist).  This module makes that explicit so changes can be
proven not to affect normal play.
"""
import functools

SIDES = {
    "GACNST": ("Allied", "盟军", frozenset({"Europeans", "UnitedStates", "Pacific"})),
    "NACNST": ("Soviet", "苏军", frozenset({"USSR", "Latin", "Chinese"})),
    "YACNST": ("Epsilon", "厄普西隆", frozenset({"PsiCorps", "Headquaters", "ScorpionCell"})),
    "FACNST": ("Foehn", "焚风", frozenset({"Guild1", "Guild2", "Guild3"})),
}
CONYARDS = frozenset(SIDES)
ALL12 = frozenset().union(*[s[2] for s in SIDES.values()])
ALL12_STR = ",".join([
    "Europeans", "UnitedStates", "Pacific",
    "USSR", "Latin", "Chinese",
    "PsiCorps", "Headquaters", "ScorpionCell",
    "Guild1", "Guild2", "Guild3",
])
TYPE_LISTS = ("BuildingTypes", "VehicleTypes", "InfantryTypes", "AircraftTypes")

# Hard-coded YR generics that MO does not redefine in [GenericPrerequisites].
BUILTIN_GENERICS = {
    "POWER": "GAPOWR,NAPOWR,NANRCT,YAPOWR,YAPOWRB,FATRAP,CAPOWR,CANRCT",
    "FACTORY": "GAWEAP,NAWEAP,YAWEAP,FAWEAP,GAWEAPB,NAWEAPB,YAWEAPB,FAWEAPB",
    "BARRACKS": "NAHAND,GAPILE,YABRCK,FABARR,GAPILEB,NAHANDB,YABRCKB,FABARRB",
    "RADAR": "GAAIRC,NARADR,YAPSIS,FACYBR",
    "TECH": "GATECH,NATECHR,NATECHC,NATEK,YAPVLT,YACVLT,YAGVLT,FACLDP",
    "PROC": "GAREFN,NAREFN,YARIREFN,FAREFN",
}


def split_list(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


class Tree:
    def __init__(self, rules):
        self.ini = rules
        self.generics = {k.upper(): split_list(v)
                         for k, v in BUILTIN_GENERICS.items()}
        for k, v in rules.items("GenericPrerequisites").items():
            self.generics[k.upper()] = split_list(v)
        self.registered = {L: rules.list_values(L) for L in TYPE_LISTS}
        self.list_of = {}
        for L, ts in self.registered.items():
            for t in ts:
                self.list_of.setdefault(t, L)
        self._cache = {}

    # ---------- prerequisite resolution ----------

    def required_conyards(self, item, depth=0):
        """Construction Yards a house MUST own to build `item`.

        A prerequisite list is AND (union of requirements); a generic
        prerequisite is OR (intersection — any option satisfies it).
        """
        key = (item, depth > 0)
        if key in self._cache:
            return self._cache[key]
        self._cache[key] = frozenset()      # cycle guard
        r = self._req(item, depth)
        self._cache[key] = r
        return r

    def _req(self, item, depth):
        if depth > 10:
            return frozenset()
        if item in CONYARDS:
            return frozenset([item])
        up = item.upper()
        if up in self.generics:
            opts = [set(self.required_conyards(x, depth + 1))
                    for x in self.generics[up]]
            return frozenset(set.intersection(*opts)) if opts else frozenset()
        pre = self.ini.get(item, "Prerequisite")
        if not pre:
            return frozenset()
        out = set()
        for x in split_list(pre):
            out |= self.required_conyards(x, depth + 1)
        return frozenset(out)

    # ---------- classification ----------

    def owner_of(self, t):
        o = self.ini.get(t, "Owner")
        return frozenset(split_list(o)) if o else None

    def effective_owner(self, t):
        """Countries that can actually build t.

        MO gates by four independent tags, all verified present in Ares:
        Owner, RequiredHouses, FactoryOwners (intersect) and ForbiddenHouses
        (subtract).  Missing Owner means "anyone".
        """
        own = self.owner_of(t)
        eff = set(ALL12) if own is None else (set(own) & ALL12)
        for k in ("RequiredHouses", "FactoryOwners"):
            v = self.ini.get(t, k)
            if v:
                eff &= set(split_list(v))
        v = self.ini.get(t, "ForbiddenHouses")
        if v:
            eff -= set(split_list(v))
        return frozenset(eff)

    def classify(self, t):
        """0 = already open to all 12 countries -> nothing to do,
           1 = a whole side can build it        -> safe to open Owner,
           2 = sub-faction exclusive            -> must be cloned,
           None = unbuildable, or not uniquely rooted (prop, spawn, ...)"""
        eff = self.effective_owner(t)
        if not eff:
            return None                     # nobody can build it anyway
        if eff >= ALL12:
            return 0
        roots = self.required_conyards(t)
        if len(roots) != 1:
            return None
        side = SIDES[next(iter(roots))][2]
        return 1 if eff >= side else 2

    def groups(self):
        g1, g2, skipped = [], [], []
        for L in TYPE_LISTS:
            for t in self.registered[L]:
                c = self.classify(t)
                if c == 1:
                    g1.append((L, t))
                elif c == 2:
                    g2.append((L, t))
                elif c is None:
                    skipped.append((L, t))
        return g1, g2, skipped

    def side_of(self, t):
        roots = self.required_conyards(t)
        return next(iter(roots)) if len(roots) == 1 else None

    # ---------- buildability simulation (regression proof) ----------

    def buildable_by(self, t, country, owned):
        """Could a house of `country` owning building set `owned` build t?"""
        if country not in self.effective_owner(t):
            return False
        tl = self.ini.get(t, "TechLevel")
        if tl is not None and tl.strip().lstrip("-").isdigit() and int(tl) < 0:
            return False
        return self.prereq_met(self.ini.get(t, "Prerequisite"), owned)

    def prereq_met(self, pre, owned):
        for x in split_list(pre):
            if not self._one_met(x, owned):
                return False
        return True

    def _one_met(self, item, owned):
        up = item.upper()
        if up in self.generics:
            return any(o in owned for o in self.generics[up])
        return item in owned
