# Build System Pitfalls

Common CMake and C++ build pitfalls encountered during project scaffolding.

## CMake: `add_library` fails with no sources

**Problem:** `add_library(vs_core STATIC)` (or with a GLOB that matches nothing) fails at configure time:

```
CMake Error at csrc/CMakeLists.txt:11 (add_library):
  No SOURCES given to target: vs_core
```

**Fix options:**

1. **Stub source file** (recommended for scaffold): Add a minimal `.cpp` with no-op implementations so the library target has at least one source.

2. **Conditional in CMakeLists.txt:**
   ```cmake
   file(GLOB VS_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/*.cpp)
   if(VS_SOURCES STREQUAL "")
       add_library(vs_core STATIC)  # empty library — works in CMake 3.20+
   else()
       add_library(vs_core STATIC ${VS_SOURCES})
   endif()
   ```
   Note: `add_library(vs_core STATIC)` with zero sources works in CMake 3.20+ but may not work in older versions. The stub source approach is more portable.

3. **Use OBJECT library:** `add_library(vs_core OBJECT ${VS_SOURCES})` — an object library with no sources is valid.

## C++: `extern "C"` headers need `<cstddef>` for `size_t`

**Problem:** When declaring `extern "C"` functions in a C++ header that use `size_t`, compilation fails with:

```
error: 'size_t' has not been declared
note: 'size_t' is defined in header '<cstddef>'
```

**Cause:** `extern "C"` tells the compiler to use C linkage, but the header is still compiled as C++. The C standard headers (like `<stddef.h>`) may not be implicitly included. In C++, `size_t` is defined in `<cstddef>`, not in the C headers.

**Fix:** Add `#include <cstddef>` inside the `extern "C"` block (or at the top of the header):

```cpp
#ifdef __cplusplus
extern "C" {
#endif

#include <cstddef>

void black76_price(const double* arr, size_t n, double* out) noexcept;

#ifdef __cplusplus
}
#endif
```

## CMake: GLOB without `CONFIGURE_DEPENDS`

**Problem:** `file(GLOB SOURCES *.cpp)` doesn't detect new `.cpp` files added after CMake's configure step. You have to re-run CMake manually.

**Fix:** Use `CONFIGURE_DEPENDS`:
```cmake
file(GLOB VS_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/*.cpp)
```

## CMake: `-Werror` with unused parameters

**Problem:** `-Werror` turns unused parameter warnings into errors. Stub implementations with named-but-unused parameters will fail.

**Fix:** Use `/*name*/` (commented-out names) instead of just `name`:
```cpp
void black76_price(const double* /*fwd*/, size_t /*n*/, double* /*out*/) noexcept {}
```
