#!/usr/bin/env python3
"""Emit [[input.function_sizes]] entries for zero-sized functions in a GoldenEye decomp ELF.

Hand-written assembly in the decomp has no .size directives, so N64Recomp sees those functions as
empty. Each one's size is taken as the distance to the next function symbol in the same section.
"""
import subprocess
import sys
from collections import defaultdict

CODE_SECTIONS = {".boot", ".start", ".code", ".inflate", ".game"}

def main():
    elf = sys.argv[1]
    readelf = sys.argv[2] if len(sys.argv) > 2 else "mips-linux-gnu-readelf"
    out = subprocess.run([readelf, "-SW", elf], capture_output=True, text=True, check=True).stdout
    sections = {}
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        idx, rest = line[1:].split("]", 1)
        parts = rest.split()
        if len(parts) < 7 or not idx.strip().isdigit():
            continue
        name, typ, addr, off, size, es, flags = parts[:7]
        # .csegment is the game's data, flagged executable only because of how it's linked
        if "X" in flags and name in CODE_SECTIONS:
            sections[int(idx)] = (int(addr, 16), int(size, 16))

    out = subprocess.run([readelf, "-sW", elf], capture_output=True, text=True, check=True).stdout
    by_section = defaultdict(dict)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 8 or not parts[0].endswith(":"):
            continue
        value, size, typ, bind, vis, ndx, name = parts[1], parts[2], parts[3], parts[4], parts[5], parts[6], parts[7]
        if typ != "FUNC" or not ndx.isdigit() or int(ndx) not in sections:
            continue
        addr = int(value, 16)
        size = int(size, 0) if not size.startswith("0x") else int(size, 16)
        by_section[int(ndx)].setdefault(addr, []).append((name, size))

    entries = []
    for ndx, syms in by_section.items():
        sec_start, sec_size = sections[ndx]
        addrs = sorted(syms)
        for i, addr in enumerate(addrs):
            end = addrs[i + 1] if i + 1 < len(addrs) else sec_start + sec_size
            for name, size in syms[addr]:
                if size == 0 and end > addr:
                    entries.append((addr, name, end - addr))

    for addr, name, size in sorted(entries):
        print("[[input.function_sizes]]")
        print(f'name = "{name}"')
        print(f"size = 0x{size:X} # 0x{addr:08X}")
        print()
    print(f"# {len(entries)} functions sized", file=sys.stderr)

if __name__ == "__main__":
    main()
