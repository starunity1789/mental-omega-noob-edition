"""Westwood MIX archive reader (RA2/YR 'new format', unencrypted).

Used to pull pristine rulesmo.ini / artmo.ini / cameo PCX files out of
Mental Omega's expandmo*.mix archives.
"""
import binascii
import os
import struct


def mix_id(name: str) -> int:
    """Westwood filename hash used as the MIX index key."""
    n = name.upper().encode("ascii")
    l = len(n)
    i = l >> 2
    if l & 3:
        n += bytes([l - (i << 2)])
        for _ in range(3 - (l & 3)):
            n += bytes([n[i << 2]])
    return binascii.crc32(n) & 0xFFFFFFFF


class Mix:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        flags, = struct.unpack("<I", self.f.read(4))
        if flags != 0:
            raise ValueError(f"{path}: unsupported mix flags {flags:#010x}")
        count, = struct.unpack("<H", self.f.read(2))
        self.f.read(4)  # body size (unreliable in MO's archives)
        idx = self.f.read(count * 12)
        base = 10 + count * 12
        self.index = {}
        for i in range(count):
            fid, off, size = struct.unpack_from("<III", idx, i * 12)
            self.index[fid] = (base + off, size)

    def has(self, name):
        return mix_id(name) in self.index

    def read(self, name):
        off, size = self.index[mix_id(name)]
        self.f.seek(off)
        return self.f.read(size)

    def close(self):
        self.f.close()


def find(mix_paths, names):
    """Return {name: (mix_path, size)} for every name found."""
    out = {}
    for m in mix_paths:
        try:
            mix = Mix(m)
        except Exception:
            continue
        for n in names:
            if n not in out and mix.has(n):
                out[n] = (m, mix.index[mix_id(n)][1])
        mix.close()
    return out


def extract(mix_paths, names, dest_dir):
    """Extract each name into dest_dir. Returns list of (name, mix, bytes)."""
    os.makedirs(dest_dir, exist_ok=True)
    done = []
    for m in mix_paths:
        try:
            mix = Mix(m)
        except Exception:
            continue
        for n in list(names):
            if mix.has(n):
                data = mix.read(n)
                with open(os.path.join(dest_dir, n), "wb") as fh:
                    fh.write(data)
                done.append((n, m, len(data)))
                names = [x for x in names if x != n]
        mix.close()
    return done, names
