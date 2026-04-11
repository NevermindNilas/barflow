@echo off
REM Three-stage PGO build for barflow._core (MSVC).
REM
REM   1. Clean + build instrumented .pyd   (/LTCG:PGINSTRUMENT /GENPROFILE)
REM   2. Run training workload             (emits .pgc files)
REM   3. Merge .pgc -> .pgd, rebuild        (/LTCG:PGOPTIMIZE /USEPROFILE)
REM
REM Requires Visual Studio Build Tools with PGO support (pgomgr.exe,
REM pgort*.dll on PATH at runtime for the instrumented build).

setlocal EnableDelayedExpansion
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
    echo [pgo] vcvars64.bat failed
    exit /b 1
)
cd /d "%~dp0"

set PYD=src\barflow\_core.cp313-win_amd64.pyd
set PGD_DIR=%~dp0src\barflow
set BUILD_DIR=build

echo [pgo] stage 1/3: instrumented build (/GENPROFILE)
rd /s /q %BUILD_DIR% 2>nul
del /q %PYD% 2>nul
del /q "%PGD_DIR%\*.pgd" 2>nul
del /q "%PGD_DIR%\*.pgc" 2>nul
set BARFLOW_PGO=generate
python setup.py build_ext --inplace --force
if errorlevel 1 (
    echo [pgo] stage 1 failed
    exit /b 1
)

echo.
echo [pgo] stage 2/3: training workload
REM VCPROFILE_PATH controls where .pgc files are written.
set VCPROFILE_PATH=%PGD_DIR%
python benchmarks\pgo_train.py
if errorlevel 1 (
    echo [pgo] training failed
    exit /b 1
)

echo.
echo [pgo] stage 2.5: merging .pgc files
pushd "%PGD_DIR%"
dir /b *.pgc 2>nul
set PGC_COUNT=0
for %%f in (*.pgc) do set /a PGC_COUNT+=1
if !PGC_COUNT! EQU 0 (
    echo [pgo] no .pgc files found in %PGD_DIR%
    echo [pgo] training binary may not have written profile data
    popd
    exit /b 1
)
REM Merge all .pgc files into the single .pgd produced by the instrument
REM build. pgomgr picks up the .pgd automatically when run in its dir.
for %%f in (*.pgd) do (
    pgomgr /merge *.pgc "%%f"
    if errorlevel 1 (
        echo [pgo] pgomgr /merge failed
        popd
        exit /b 1
    )
)
popd

echo.
echo [pgo] stage 3/3: optimized build (/USEPROFILE)
rd /s /q %BUILD_DIR% 2>nul
del /q %PYD% 2>nul
set BARFLOW_PGO=use
python setup.py build_ext --inplace --force
if errorlevel 1 (
    echo [pgo] stage 3 failed
    exit /b 1
)

echo.
echo [pgo] cleaning up profile artifacts
del /q "%PGD_DIR%\*.pgc" 2>nul
del /q "%PGD_DIR%\*.pgd" 2>nul

echo.
echo [pgo] done. Optimized .pyd at %PYD%
endlocal
