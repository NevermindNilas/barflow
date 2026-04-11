import os
import sys
from setuptools import setup, Extension

# PGO mode selection via env var BARFLOW_PGO:
#   (unset)    -- standard build (default)
#   "generate" -- MSVC: /GENPROFILE instrumented build (no /LTCG, no /OPT:REF/ICF)
#                 GCC/Clang: -fprofile-generate
#   "use"      -- MSVC: /USEPROFILE optimized build (merged .pgd must exist)
#                 GCC/Clang: -fprofile-use
BARFLOW_PGO = os.environ.get("BARFLOW_PGO", "").strip().lower()
if BARFLOW_PGO and BARFLOW_PGO not in ("generate", "use"):
    raise SystemExit(f"BARFLOW_PGO must be 'generate' or 'use', got: {BARFLOW_PGO!r}")

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
# PGO (profile-guided optimization):
#   Set BARFLOW_PGO=generate to produce an instrumented build, run the
#   training workload (benchmarks/pgo_train.py), then set BARFLOW_PGO=use
#   to produce the final optimized build. Scripts build_pgo.bat (Windows)
#   and build_pgo.sh (POSIX) automate the three-step flow.
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
    if BARFLOW_PGO == "generate":
        # Instrumented build: /LTCG:PGINSTRUMENT replaces plain /LTCG and
        # /GENPROFILE inserts probes. /OPT:REF/ICF are incompatible with
        # instrumentation and would prevent .pgc generation, so strip them.
        extra_link_args = [
            "/LTCG:PGINSTRUMENT",
            "/GENPROFILE",
            "/DEBUG:NONE",
        ]
    elif BARFLOW_PGO == "use":
        # Optimized build: consume merged profile data (.pgd) alongside the
        # link. /LTCG:PGOPTIMIZE + /USEPROFILE is the standard pair.
        # MSVC requires /OPT:REF/ICF to match between GENPROFILE and
        # USEPROFILE links — since the instrument build can't use them,
        # the use build must also omit them. PGO's own dead-code folding
        # (based on profile data) largely compensates.
        extra_link_args = [
            "/LTCG:PGOPTIMIZE",
            "/USEPROFILE",
            "/DEBUG:NONE",
        ]
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
    if BARFLOW_PGO == "generate":
        extra_compile_args.append("-fprofile-generate")
        extra_link_args.append("-fprofile-generate")
    elif BARFLOW_PGO == "use":
        extra_compile_args.append("-fprofile-use")
        extra_link_args.append("-fprofile-use")
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
    if BARFLOW_PGO == "generate":
        extra_compile_args.append("-fprofile-generate")
        extra_link_args.append("-fprofile-generate")
    elif BARFLOW_PGO == "use":
        extra_compile_args.append("-fprofile-use")
        extra_link_args.append("-fprofile-use")

ext = Extension(
    "barflow._core",
    sources=["src/barflow/_core.cpp"],
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    libraries=libraries,
    language="c++",
)

setup(ext_modules=[ext])
