import sys
from setuptools import setup, Extension

# -----------------------------------------------------------------------------
# Aggressive (but portable) build optimization flags for barflow._core
# -----------------------------------------------------------------------------
#
# MSVC (Windows) flags:
#   /std:c++17   -- C++17 language level
#   /O2          -- Maximize speed (standard release optimization)
#   /Ob3         -- Aggressive inlining (stronger than /Ob2). Requires
#                   Visual Studio 2019 16.0+. MSVC silently downgrades to
#                   /Ob2 on older toolchains, so it's safe to pass.
#   /Oi          -- Generate intrinsic functions (memcpy, memset, etc.)
#   /GL          -- Whole program optimization (enables cross-TU inlining).
#                   Must be paired with /LTCG at link time.
#   /Gw          -- Put each global/static in its own COMDAT so the linker
#                   can strip unreferenced data (better DCE with /OPT:REF).
#   /Zc:inline   -- Remove unreferenced inline functions/data (smaller .obj,
#                   faster link, better DCE).
#   /EHsc        -- Standard C++ exception handling.
#   /W3          -- Reasonable warning level.
#   /DNDEBUG     -- Define NDEBUG (disables asserts) for release builds.
#
# MSVC linker flags:
#   /LTCG        -- Link-time code generation, pairs with /GL.
#   /OPT:REF     -- Eliminate unreferenced functions/data (dead code strip).
#   /OPT:ICF     -- Identical COMDAT folding (merge identical functions).
#   /DEBUG:NONE  -- Do not emit a PDB; keeps wheels small and reproducible.
#
# Deliberately NOT added:
#   /GS-         -- Disables stack buffer security cookies; security regression.
#   /arch:AVX2   -- Would break wheels on pre-Haswell CPUs (we ship binaries).
#   /fp:fast     -- We don't do heavy FP; not worth the semantic changes.
#
# GCC / Clang (POSIX) flags:
#   -std=c++17          -- C++17 language level.
#   -O3                 -- Full optimization.
#   -DNDEBUG            -- Disable asserts.
#   -fvisibility=hidden -- Only explicitly exported symbols are visible;
#                          lets the optimizer assume internal linkage and
#                          shrinks the dynamic symbol table.
#   -flto               -- Link-time optimization (whole program, cross-TU
#                          inlining, DCE). Must also be passed at link time.
#   -ffunction-sections,
#   -fdata-sections     -- Each function/datum in its own section so the
#                          linker can GC unreferenced ones.
#   -fno-plt            -- (Linux only) skip the PLT for external calls in
#                          position-independent code; small call-site win.
#
# GCC / Clang linker flags:
#   -flto                 -- Match the compile-time LTO flag.
#   -Wl,--gc-sections     -- (Linux) strip unreferenced sections.
#   -Wl,-dead_strip       -- (macOS) equivalent dead-code stripping.
#
# Cross-platform:
#   - NDEBUG is defined explicitly on every platform (do not rely on the
#     caller's distutils config; pip/cibuildwheel invocations vary).
#   - Py_LIMITED_API is intentionally NOT set: barflow._core uses the full
#     CPython C API (tp_iternext fast path, PyObject layout assumptions).
# -----------------------------------------------------------------------------

if sys.platform == "win32":
    extra_compile_args = [
        "/std:c++17",
        "/O2",
        "/Ob3",
        "/Oi",
        "/GL",
        "/Gw",
        "/Zc:inline",
        "/EHsc",
        "/W3",
        "/DNDEBUG",
    ]
    extra_link_args = [
        "/LTCG",
        "/OPT:REF",
        "/OPT:ICF",
        "/DEBUG:NONE",
    ]
    libraries = ["kernel32"]
elif sys.platform == "darwin":
    extra_compile_args = [
        "-std=c++17",
        "-O3",
        "-DNDEBUG",
        "-fvisibility=hidden",
        "-flto",
        "-ffunction-sections",
        "-fdata-sections",
    ]
    extra_link_args = [
        "-flto",
        "-Wl,-dead_strip",
    ]
    libraries = []
else:
    # Linux / other POSIX
    extra_compile_args = [
        "-std=c++17",
        "-O3",
        "-DNDEBUG",
        "-fvisibility=hidden",
        "-flto",
        "-fno-plt",
        "-ffunction-sections",
        "-fdata-sections",
    ]
    extra_link_args = [
        "-flto",
        "-Wl,--gc-sections",
    ]
    libraries = []

ext = Extension(
    "barflow._core",
    sources=["src/barflow/_core.cpp"],
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    libraries=libraries,
    language="c++",
)

setup(ext_modules=[ext])
