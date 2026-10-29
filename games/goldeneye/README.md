# GoldenEye 007 (US) recompilation config

This folder holds what N64Recomp needs to recompile GoldenEye 007 (US). It contains no game code or data.
You supply your own ROM, build the [n64decomp/007](https://github.com/n64decomp/007) decompilation from
it to get a symbol-rich ELF, and point N64Recomp at that ELF.

## Steps

1. Build the decomp (Linux/WSL, needs `binutils-mips-linux-gnu`, `make`, `python3`, `gcc`):
   ```bash
   git clone https://github.com/n64decomp/007.git && cd 007
   cp /path/to/your/GoldenEye_007_U.z64 baserom.u.z64   # sha1 abe01e4aeb033b6c0836819f549c791b26cfde83
   ./scripts/extract_baserom.u.sh
   make VERSION=US                                      # ends with "MATCH!"
   ```
2. Copy `build/u/ge007.u.elf` into this folder.
3. Generate sizes for the hand-written assembly functions and recompile:
   ```bash
   python3 tools/gen_func_sizes.py ge007.u.elf > func_sizes.toml
   cat us.toml func_sizes.toml > build.toml
   mkdir -p RecompiledFuncs
   N64Recomp build.toml
   ```

This currently produces about 8,400 recompiled functions in `RecompiledFuncs/` with no errors.

## Notes on GoldenEye's memory layout

- The game runs its code from TLB-mapped addresses: libultra at `0x70000450` (a mirror of KSEG0) and the main
  game code at `0x7F000000`, which is rarezip-compressed in the ROM and inflated at boot.
- All of the game's data, rodata and bss live in KSEG0 (`.csegment` at `0x80020D90`, `.bss` at `0x8005D2E0`).
  The only data at mapped addresses belongs to the boot-time inflater in `.inflate` (`0x70200000`).
- Because recompiled code doesn't need to be in RDRAM, the runtime can skip the inflate and TLB setup and
  resolve `0x70xxxxxx`/`0x7Fxxxxxx` function pointers through its function lookup. That should let the stock
  decomp ELF run without the TLB-free, uncompressed decomp branch that GoldenRecomp relies on. This still has
  to be proven in a runtime.
- Some of the game's jump tables live in `.csegment` rather than next to the code that uses them. This needs
  the cross-section jump table support added to N64Recomp in this fork; upstream N64Recomp fails on
  `renderGunbarrelEyeIntroSequence`.
- The entries under `ignored` are boot, exception, cop0 and TLB routines (plus a few data labels the decomp
  marks as functions). The runtime provides equivalents.

## Prior work

- [GoldenRecomp](https://github.com/KholdFuzion/GoldenRecomp) (KholdFuzion, SonicDcer): a working
  N64Recomp port built on a TLB-free decomp branch that is no longer public.
- [goldeneye-pc-port](https://github.com/jkdansereau/goldeneye-pc-port): a source port of the decomp, not a
  recompilation.
