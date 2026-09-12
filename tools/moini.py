"""Line-surgical INI editor for Mental Omega rules/art files.

Everything is kept as the original list of lines; edits touch only the exact
lines they need to.  That way a diff against the pristine file shows precisely
the intended changes and nothing else.
"""
import re

SEC_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(;.*)?$")


class Ini:
    def __init__(self, path, encoding="latin-1"):
        self.path = path
        self.encoding = encoding
        raw = open(path, "r", encoding=encoding, newline="").read()
        self.newline = "\r\n" if "\r\n" in raw else "\n"
        self.lines = raw.split(self.newline)
        self._reindex()

    def _reindex(self):
        self.sections = {}          # name -> list of (start, end) line ranges
        self._order = []            # section names in file order
        cur, start = None, None
        for i, ln in enumerate(self.lines):
            m = SEC_RE.match(ln)
            if m:
                if cur is not None:
                    self.sections.setdefault(cur, []).append((start, i))
                cur, start = m.group(1).strip(), i
                self._order.append(cur)
        if cur is not None:
            self.sections.setdefault(cur, []).append((start, len(self.lines)))

    # ---------- reading ----------

    def has_section(self, name):
        return name in self.sections

    def duplicates(self):
        return {k: len(v) for k, v in self.sections.items() if len(v) > 1}

    def _key_lines(self, name, key):
        """[(line_index, value)] for every occurrence of key in section name."""
        out = []
        kl = key.lower()
        for start, end in self.sections.get(name, []):
            for i in range(start + 1, end):
                s = self.lines[i].strip()
                if not s or s.startswith(";"):
                    continue
                if "=" in s and s.split("=", 1)[0].strip().lower() == kl:
                    out.append((i, s.split("=", 1)[1]))
        return out

    def get(self, name, key, default=None):
        ks = self._key_lines(name, key)
        if not ks:
            return default
        return ks[-1][1].split(";")[0].strip()

    def items(self, name):
        """Effective key/value map of a section (last occurrence wins)."""
        out = {}
        for start, end in self.sections.get(name, []):
            for i in range(start + 1, end):
                s = self.lines[i].strip()
                if not s or s.startswith(";") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                out[k.strip()] = v.split(";")[0].strip()
        return out

    def list_values(self, name):
        """Values of an index=VALUE registration list, in order."""
        out = []
        for start, end in self.sections.get(name, []):
            for i in range(start + 1, end):
                s = self.lines[i].strip()
                if not s or s.startswith(";") or "=" not in s:
                    continue
                v = s.split("=", 1)[1].split(";")[0].strip()
                if v:
                    out.append(v)
        return out

    def section_names(self):
        return list(self._order)

    # ---------- editing ----------

    def set_key(self, name, key, value):
        """Set key in an existing section. Rewrites every occurrence so the
        effective value is unambiguous. Returns number of lines touched."""
        ks = self._key_lines(name, key)
        if ks:
            for i, _ in ks:
                indent = re.match(r"^(\s*)", self.lines[i]).group(1)
                self.lines[i] = f"{indent}{key}={value}"
            return len(ks)
        # not present: insert right after the (last) section header
        start, end = self.sections[name][-1]
        self.lines.insert(start + 1, f"{key}={value}")
        self._reindex()
        return 1

    def rewrite_key_value(self, name, key, new_value):
        return self.set_key(name, key, new_value)

    def delete_key(self, name, key):
        """Remove every occurrence of key from a section. Returns count."""
        ks = self._key_lines(name, key)
        for i, _ in sorted(ks, reverse=True):
            del self.lines[i]
        if ks:
            self._reindex()
        return len(ks)

    def append_section(self, name, pairs, comment=None):
        """Append a brand-new section at end of file."""
        if self.lines and self.lines[-1].strip() != "":
            self.lines.append("")
        if comment:
            self.lines.append(f"; {comment}")
        self.lines.append(f"[{name}]")
        for k, v in pairs:
            self.lines.append(f"{k}={v}")
        self._reindex()

    def append_to_list(self, name, values):
        """Append entries to an index=VALUE registration list, continuing the
        highest existing numeric index."""
        idxs = []
        for start, end in self.sections.get(name, []):
            for i in range(start + 1, end):
                s = self.lines[i].strip()
                if "=" in s and not s.startswith(";"):
                    k = s.split("=", 1)[0].strip()
                    if k.isdigit():
                        idxs.append(int(k))
        nxt = (max(idxs) + 1) if idxs else 0
        start, end = self.sections[name][-1]
        ins = end
        while ins > start + 1 and self.lines[ins - 1].strip() == "":
            ins -= 1
        block = [f"{nxt + n}={v}" for n, v in enumerate(values)]
        self.lines[ins:ins] = block
        self._reindex()
        return nxt

    def delete_section(self, name):
        """Remove every occurrence of a section, header and body."""
        n = 0
        for start, end in sorted(self.sections.get(name, []), reverse=True):
            del self.lines[start:end]
            n += 1
        self._reindex()
        return n

    def delete_lines_matching(self, name, pattern):
        """Delete lines in a section matching a regex. Returns deleted text."""
        rx = re.compile(pattern, re.I)
        killed = []
        for start, end in sorted(self.sections.get(name, []), reverse=True):
            for i in range(end - 1, start, -1):
                if rx.match(self.lines[i].strip()):
                    killed.append(self.lines[i])
                    del self.lines[i]
        self._reindex()
        return killed

    def save(self, path=None):
        path = path or self.path
        with open(path, "w", encoding=self.encoding, newline="") as fh:
            fh.write(self.newline.join(self.lines))
        return path
