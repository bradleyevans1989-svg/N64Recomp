# Worms Armageddon (US) recompilation config

This folder holds what N64Recomp needs to recompile Worms Armageddon (US). It contains no game code or data.
There is no decompilation of this game, so instead of an ELF, N64Recomp reads the ROM directly together with
`syms.us.toml`, a list of every function's address and size built with splat/spimdisasm plus hand-identified
libultra names.

ROM: `Worms Armageddon (USA)`, game code `NADE`, revision 0, 12 MiB, CIC-6102,
sha1 `3b17b36ba91737b86aa56ecb1b48a89444b53572`.

## Steps

1. Copy your ROM into this folder as `baserom.z64` (it is gitignored, never commit it).
2. Recompile with the checked-in symbols:
   ```bash
   N64Recomp us.toml
   ```
   This produces 2,570 recompiled functions in `RecompiledFuncs/` with no errors or warnings, and the
   output compiles with clang.

To regenerate `syms.us.toml` from scratch (needs `pip install splat64[mips] spimdisasm`):

```bash
python3 -m splat split splat.us.yaml
python3 tools/splat2syms.py asm baserom.z64 syms.us.toml libultra_names.txt
```

## Memory layout

| Segment | ROM | VRAM | Notes |
|---|---|---|---|
| boot | `0x001000`-`0x038D40` | `0x80000400` | rodata/vtables `0x1040`, text `0x3CB0`-`0x34FD0`, libultra in `0x80025860`-`0x800343C8` |
| boot bss | | `0x80038140`-`0x80048FE0` | cleared by the entrypoint |
| ovl_a | `0x038D40`-`0x07F0B0` | `0x80048FE0` | data first, text from ROM `0x3E790` |
| ovl_b | `0x07F0B0`-`0x0E81C0` | `0x80048FE0` | data first, text from ROM `0x83930` |
| assets | `0x0E81C0`-`0xBF51A4` | | sprites, sound and other data, loaded through the game's file reader |

- Nothing is compressed. The two overlays share the same VRAM and are swapped in by `func_8000405C`, which
  DMAs one of them to `0x80048FE0` with `func_8002FEB0` (the game's DMA wrapper around `osPiStartDma`).
  The runtime has to register the matching section when that DMA happens (`load_overlays`), and calls from
  boot into `0x80048FE0`+ are resolved at runtime through the function lookup.
- The game is C++ built with KMC GCC. Virtual calls go through g++ 2.x vtables (`lh` delta, `lw` pointer,
  `jalr`), so there are many indirect calls. These also go through the function lookup.
- After loading `ovl_b`, the loader clears 0x1120 bytes at `0xB00E7090`, a cartridge address. On hardware that
  write does nothing, but in a recompiled build it lands outside RDRAM, so it will need a patch or a guard in
  the runtime.

## How the symbols were made

- splat/spimdisasm find the function boundaries in each text range. `tools/splat2syms.py` then splits the
  runs of hand-written libultra assembly that splat folds into one function, at `alabel`s, jal targets and
  address-taken entry points (such as thread entry functions).
- `libultra_names.txt` names 117 libultra functions found by hand from their hardware register use, cop0 and
  cache instructions, and call graph. N64Recomp needs these names so it can swap in the runtime's
  reimplementations and skip the exception, thread and TLB code.
- `osUnmapTLBAll` (`func_8002CE70`) is stubbed rather than named, because the game's boot code calls it
  directly.
- Overlay function names start with `ovl_a_` or `ovl_b_` so the two overlays don't collide.

## Status and next steps

The recompiler side is done. A runnable port still needs a runtime project built on
[N64ModernRuntime](https://github.com/N64Recomp/N64ModernRuntime) (like Zelda64Recomp), which means:
registering the two overlays, handling the `0xB00E7090` write, hooking up the graphics renderer (RT64),
audio and input, and then fixing crashes as they come up.
