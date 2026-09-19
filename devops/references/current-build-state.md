# pCloud Console Client — Current Build State

## Status (2026-05-06)
Build succeeds cleanly on Ubuntu 26.04 with GCC 14+ and CMake 4.2. No source patches needed.

## Build command
```bash
cd ~/sources/console-client/pCloudCC/build
cmake ..
make -j$(nproc)
```

## Output
- Binary: `~/sources/console-client/pCloudCC/build/pcloudcc`
- No `pclsync` or `pcloudcc_lib` standalone binaries — only the main `pcloudcc` binary.

## Dependencies (all installed)
- libboost-program-options-dev 1.90.0
- libfuse-dev 2.9.9
- libfuse2t64 2.9.9
- libfuse3-4 3.18.2
- cmake 4.2

## Known issues
- None. Previous blockers (DELIM macros, psynclib.c casts, missing libboost) are resolved.
- CMake policy CMP0167 warning (FindBoost deprecated) — harmless, suppress with `-Wno-dev`.
