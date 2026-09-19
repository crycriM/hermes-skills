# Common Build Errors for pCloud Console Client

## Boost not found
**Error:** `Could not find a package configuration file provided by "boost_system"`
**Fix:** `sudo apt-get install libboost-system-dev libboost-program-options-dev`. If CMake still fails, set `BOOST_ROOT=/usr`.

## FUSE include errors
**Error:** `fatal error: fuse.h: No such file or directory`
**Fix:** Locate the header: `find /usr/include -name fuse.h`. Then patch `lib/pclsync/pfs.c` and `lib/pclsync/pfsxattr.c` with:
```bash
sed -i 's|#include <fuse.h>|#include <fuse/fuse.h>|' lib/pclsync/pfs.c lib/pclsync/pfsxattr.c
```

## DELIM_SEMICOLON / DELIM_DIR macro errors
**Error:** `passing argument 3 of 'parse_os_path' makes pointer from integer without a cast`
**Fix:** Ensure the macros are defined as single characters:
```c
#define DELIM_SEMICOLON ';'
#define DELIM_DIR '/'
```
Apply the changes in `lib/pclsync/ptools.h` and re‑run `make clean && make fs`.

## CMake policy warnings
**Error:** `Compatibility with CMake < 3.10 will be removed...`
**Fix:** Use `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` when configuring.

## Linking errors after make
**Error:** `undefined reference to 'pthread_...'`
**Fix:** Ensure `-lpthread` is in the link line. Add `target_link_libraries(pcloudcc_lib ${PCLSYNC_PATH}/psynclib.a ${MBEDTLS_PATH}/library/libmbedtls.a fuse pthread sqlite3 udev` in `CMakeLists.txt` if missing.

## General tip
Run `make VERBOSE=1` to see full compiler commands when an error occurs.
