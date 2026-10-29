"""Convert splat/spimdisasm asm output into an N64Recomp symbols toml.

splat folds runs of handwritten asm (libultra) into one function and marks the
inner entry points with alabel. Split those back out, along with any jal target
that lands inside another function's range.
"""
import re, struct, sys
from pathlib import Path

asm_dir = Path(sys.argv[1])
rom = Path(sys.argv[2]).read_bytes()
out = Path(sys.argv[3])
names_path = Path(sys.argv[4]) if len(sys.argv) > 4 else None

# name, rom, vram, size, text files, text rom range
SECTIONS = [
    ("boot", 0x1000, 0x80000400, 0x38D40 - 0x1000, ["entry.s", "boot_text.s"]),
    ("ovl_a", 0x38D40, 0x80048FE0, 0x7F0B0 - 0x38D40, ["ovl_a_text.s"]),
    ("ovl_b", 0x7F0B0, 0x80048FE0, 0xE81C0 - 0x7F0B0, ["ovl_b_text.s"]),
]
nm_re = re.compile(r"^nonmatching (\w+), (0x[0-9A-Fa-f]+)")
al_re = re.compile(r"^\s*alabel (\w+)")
ins_re = re.compile(r"/\* ([0-9A-F]+) ([0-9A-F]{8}) ([0-9A-F]{8}) \*/")

def word(off):
    return struct.unpack(">I", rom[off:off + 4])[0]

def parse(path):
    funcs, alabels, jals = [], [], set()
    cur = None
    pending_alabel = None
    for line in path.read_text().splitlines():
        m = nm_re.match(line)
        if m:
            cur = [m.group(1), None, int(m.group(2), 16)]
            funcs.append(cur)
            continue
        m = al_re.match(line)
        if m:
            pending_alabel = m.group(1)
            continue
        m = ins_re.search(line)
        if m:
            vram = int(m.group(2), 16)
            w = int(m.group(3), 16)
            if cur is not None and cur[1] is None:
                cur[1] = vram
            if pending_alabel:
                alabels.append(vram)
                pending_alabel = None
            if w >> 26 == 3:
                jals.add(0x80000000 | ((w & 0x3FFFFFF) << 2))
            # Address-taken code (thread entry points, function pointers).
            for ref in re.findall(r"%hi\((?:D|func)_([0-9A-F]{8})\)", line):
                jals.add(int(ref, 16))
    return funcs, alabels, jals

# Only trust jal targets from the section's own code: calls between the
# overlays and boot are ambiguous since both overlays share one vram range.
parsed = {}
for sec in SECTIONS:
    fl, al, jl = [], [], set()
    for f in sec[4]:
        a, b, j = parse(asm_dir / f)
        fl += a; al += b; jl |= j
    parsed[sec[0]] = (fl, al, jl)

names = {}
if names_path and names_path.exists():
    for line in names_path.read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            n, a = line.split("=")
            names[int(a.strip(), 16)] = n.strip()

lines = []
total = 0
for name, srom, svram, ssize, _ in SECTIONS:
    funcs, alabels, all_jals = parsed[name]
    funcs.sort(key=lambda f: f[1])
    starts = {f[1] for f in funcs}
    ends = {f[1]: f[1] + f[2] for f in funcs}
    extra = set(alabels)
    for t in all_jals:
        if t in starts:
            continue
        for s in starts:
            if s < t < ends[s]:
                r = t - svram + srom
                prev = word(r - 8)
                if prev == 0x03E00008 or word(r - 4) == 0:
                    extra.add(t)
                break
    cuts = sorted(starts | extra)
    func_end = {}
    for f in funcs:
        func_end[f[1]] = f[1] + f[2]
    out_funcs = []
    for i, s in enumerate(cuts):
        parent = max(p for p in starts if p <= s)
        end = func_end[parent]
        nxt = cuts[i + 1] if i + 1 < len(cuts) else end
        e = min(end, nxt)
        if e <= s:
            continue
        fname = names.get(s) if name == "boot" else None
        if fname is None:
            fname = f"func_{s:08X}" if name == "boot" else f"{name}_func_{s:08X}"
            if s == 0x80000400 and name == "boot":
                fname = "entrypoint"
        out_funcs.append((fname, s, e - s))
    lines += ["[[section]]", f'name = "{name}"', f"rom = 0x{srom:08X}",
              f"vram = 0x{svram:08X}", f"size = 0x{ssize:X}", "functions = ["]
    for fname, s, sz in out_funcs:
        lines.append(f'    {{ name = "{fname}", vram = 0x{s:08X}, size = 0x{sz:X} }},')
    lines += ["]", ""]
    total += len(out_funcs)
    print(name, len(out_funcs), "functions", f"({len(extra)} split points added)")
out.write_text("\n".join(lines))
print("total", total)
