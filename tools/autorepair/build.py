"""Build MOAutoRepair.dll (32-bit Syringe plugin) and check it is what Syringe expects.

    python tools/autorepair/build.py

Compiler: zig's clang (pip install ziglang), no C runtime, no imports at all.
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "AutoRepair.c")
DLL = os.path.join(HERE, "MOAutoRepair.dll")
HOOKS = {0x55D360: (5, "AutoRepair_MainLoop")}


def build():
    for f in ("MOAutoRepair.dll", "MOAutoRepair.lib", "MOAutoRepair.pdb"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            os.remove(p)
    cmd = [sys.executable, "-m", "ziglang", "cc", "-target", "x86-windows-gnu",
           "-shared", "-O2", "-Wall", "-Wextra", "-Werror", "-fno-stack-protector",
           "-nostdlib", "-s", "-Wl,--entry=DllMainCRTStartup",
           "-o", DLL, SRC]
    subprocess.run(cmd, check=True, cwd=HERE)
    for f in ("MOAutoRepair.lib", "MOAutoRepair.pdb", "AutoRepair.lib"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            os.remove(p)
    check()


def check():
    import pefile
    pe = pefile.PE(DLL)
    base = pe.OPTIONAL_HEADER.ImageBase
    assert pe.FILE_HEADER.Machine == 0x14C, "not a 32-bit DLL"
    sec = [s for s in pe.sections if s.Name.startswith(b".syhks")]
    assert len(sec) == 1, "no .syhks00 section"
    data = sec[0].get_data()
    found = {}
    for i in range(0, len(data) - 15, 16):
        addr, size, name_ptr, _ = struct.unpack_from("<IIII", data, i)
        if addr:
            found[addr] = (size, pe.get_data(name_ptr - base, 64).split(b"\0")[0].decode())
    assert found == HOOKS, found
    exports = {e.name.decode() for e in pe.DIRECTORY_ENTRY_EXPORT.symbols}
    assert {n for _, n in HOOKS.values()} <= exports, exports
    imports = {e.dll.decode().lower() for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])}
    assert imports <= {"kernel32.dll"}, imports
    print(f"MOAutoRepair.dll ok: {os.path.getsize(DLL)} bytes, hooks {found}, "
          f"imports {sorted(imports) or 'none'}")


if __name__ == "__main__":
    build()
