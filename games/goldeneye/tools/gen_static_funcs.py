#!/usr/bin/env python3
"""Emit [[input.manual_funcs]] entries for static functions that have no ELF symbol.

IDO keeps static functions out of the ELF symbol table, but each object file's .mdebug section still lists them as
procedure symbols. This reads the linker map to find where each object's .text landed, then reads that object's
.mdebug local symbols to recover the static function addresses. Sizes come from the next function in the section.

Usage: gen_static_funcs.py <decomp dir> <map file> <elf file>  > static_funcs.toml
"""
import re
import struct
import subprocess
import sys
from pathlib import Path

SECTIONS = {".code", ".game"}
ST_PROC, ST_STATICPROC = 6, 14


def read_elf_sections(path):
    data = Path(path).read_bytes()
    shoff, = struct.unpack_from(">I", data, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from(">HHH", data, 0x2E)
    headers = [struct.unpack_from(">IIIIIIIIII", data, shoff + i * shentsize) for i in range(shnum)]
    strtab = headers[shstrndx]
    def name(off):
        start = strtab[4] + off
        return data[start:data.index(b"\0", start)].decode()
    return data, {name(h[0]): h for h in headers}


def mdebug_procs(obj_path):
    """Returns [(name, text_offset, is_static)] for procedures in an object's .mdebug."""
    data, sections = read_elf_sections(obj_path)
    if ".mdebug" not in sections:
        return []
    hdr = sections[".mdebug"][4]
    fields = struct.unpack_from(">HH" + "I" * 23, data, hdr)
    (magic, _, _, _, _, _, _, _, _, isym_max, cb_sym_off, _, _, _, _, iss_max, cb_ss_off, _, _,
     ifd_max, cb_fd_off, _, _, _, _) = fields
    if magic != 0x7009:
        return []
    procs = []
    # FDR is 72 bytes: adr, rss, issBase, cbSs, isymBase, csym, ...
    for f in range(ifd_max):
        fdr = cb_fd_off + f * 72
        _, _, iss_base, _, isym_base, csym = struct.unpack_from(">IiiiII", data, fdr)
        for s in range(isym_base, isym_base + csym):
            iss, value, bits = struct.unpack_from(">iII", data, cb_sym_off + s * 12)
            st = bits >> 26
            if st in (ST_PROC, ST_STATICPROC):
                start = cb_ss_off + iss_base + iss
                name = data[start:data.index(b"\0", start)].decode()
                procs.append((name, value, st == ST_STATICPROC))
    return procs


def main():
    decomp, map_path, elf_path = sys.argv[1:4]
    # Placement of each object's .text from the linker map.
    placements = []
    lines = Path(map_path).read_text().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^ \.text\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+\.o)$", line)
        if m:
            placements.append((int(m.group(1), 16), int(m.group(2), 16), m.group(3)))

    # Existing function symbols and section bounds from the final ELF.
    out = subprocess.run(["readelf", "-sW", elf_path], capture_output=True, text=True, check=True).stdout
    known = {}
    for row in out.splitlines():
        cols = row.split()
        if len(cols) >= 8 and cols[3] == "FUNC" and cols[6] != "UND":
            known[int(cols[1], 16)] = cols[7]
    _, elf_sections = read_elf_sections(elf_path)
    bounds = [(h[3], h[3] + h[5]) for n, h in elf_sections.items() if n in SECTIONS]

    statics = {}
    for addr, size, obj in placements:
        if not any(lo <= addr < hi for lo, hi in bounds):
            continue
        obj_path = Path(decomp) / obj
        if not obj_path.exists():
            continue
        for name, offset, is_static in mdebug_procs(obj_path):
            vram = addr + offset
            if is_static and vram not in known and offset < size:
                statics[vram] = name

    # Sizes run to the next function start (known or static) or the end of the section.
    starts = sorted(set(known) | set(statics))
    used = set(known.values())
    for vram in sorted(statics):
        section = next((elf_sections[n] for n in SECTIONS if elf_sections[n][3] <= vram < elf_sections[n][3] + elf_sections[n][5]))
        end = section[3] + section[5]
        nxt = next((s for s in starts if s > vram), end)
        name = statics[vram]
        if name in used:
            name = f"{name}_{vram:08X}"
        used.add(name)
        print("[[input.manual_funcs]]")
        print(f'name = "{name}"')
        print(f'section = "{next(n for n in SECTIONS if elf_sections[n] is section)}"')
        print(f"vram = 0x{vram:08X}")
        print(f"size = 0x{min(nxt, end) - vram:X}")
        print()


if __name__ == "__main__":
    main()
