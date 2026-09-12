"""Reader/writer for Westwood CSF string tables (ra2md.csf).

Layout: ' FSC' header, then one ' LBL' record per label.  Value records are
tagged ' RTS' (plain) or 'WRTS' (plain + an extra ASCII payload).  String data
is UTF-16LE with every byte bitwise-inverted.
"""
import struct

HDR = b" FSC"
LBL = b" LBL"
STR = b" RTS"
WSTR = b"WRTS"


def _dec(raw):
    return bytes(~b & 0xFF for b in raw).decode("utf-16-le")


def _enc(s):
    return bytes(~b & 0xFF for b in s.encode("utf-16-le"))


class Csf:
    def __init__(self, path):
        d = open(path, "rb").read()
        if d[:4] != HDR:
            raise ValueError("not a CSF file")
        self.version, nlbl, self.nstrings, self.unused, self.language = \
            struct.unpack_from("<IIIII", d, 4)
        self.labels = []                       # [(name, [(tag, value, extra)])]
        p = 24
        for _ in range(nlbl):
            if d[p:p + 4] != LBL:
                raise ValueError(f"desync at {p}")
            p += 4
            cnt, ln = struct.unpack_from("<II", d, p)
            p += 8
            name = d[p:p + ln].decode("ascii")
            p += ln
            vals = []
            for _ in range(cnt):
                tag = d[p:p + 4]
                p += 4
                vlen, = struct.unpack_from("<I", d, p)
                p += 4
                val = _dec(d[p:p + vlen * 2])
                p += vlen * 2
                extra = None
                if tag == WSTR:
                    el, = struct.unpack_from("<I", d, p)
                    p += 4
                    extra = d[p:p + el]
                    p += el
                vals.append((tag, val, extra))
            self.labels.append((name, vals))
        self._index = {n: i for i, (n, _) in enumerate(self.labels)}

    def get(self, name):
        i = self._index.get(name)
        return self.labels[i][1][0][1] if i is not None and self.labels[i][1] else None

    def has(self, name):
        return name in self._index

    def set(self, name, value):
        """Add or replace a single-value label. Returns 'added' or 'replaced'."""
        if name in self._index:
            i = self._index[name]
            self.labels[i] = (name, [(STR, value, None)])
            return "replaced"
        self.labels.append((name, [(STR, value, None)]))
        self._index[name] = len(self.labels) - 1
        return "added"

    def save(self, path):
        out = bytearray()
        nstr = 0
        for name, vals in self.labels:
            out += LBL
            out += struct.pack("<II", len(vals), len(name))
            out += name.encode("ascii")
            for tag, val, extra in vals:
                nstr += 1
                out += tag
                out += struct.pack("<I", len(val))
                out += _enc(val)
                if tag == WSTR:
                    out += struct.pack("<I", len(extra))
                    out += extra
        hdr = HDR + struct.pack("<IIIII", self.version, len(self.labels),
                                nstr, self.unused, self.language)
        with open(path, "wb") as fh:
            fh.write(hdr + bytes(out))
        return path
