@echo off
chcp 65001 >nul
setlocal
rem ============================================================
rem  cinescene - desktop (Windows + NVIDIA) render launcher
rem  Double-click, or run from cmd inside the cinescene folder.
rem ============================================================
cd /d "%~dp0\..\.."

rem --- Blender location (edit if you installed elsewhere) ---
if "%BLENDER%"=="" set "BLENDER=C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
if not exist "%BLENDER%" (
  echo [!] Blender not found at "%BLENDER%"
  echo     Set it first, e.g.:  set BLENDER=D:\Blender\blender.exe
  pause & exit /b 1
)

rem --- use the asset cache shipped in this pack (identical result, works offline) ---
set "CINESCENE_CACHE=%CD%\asset_cache"
rem --- 6 GB VRAM card: allow up to 12 GB system-side estimate ---
set "CINESCENE_MEM_LIMIT_GB=12"

echo.
echo  0 = SPEED TEST: final quality, 11 frames (1 per second)  ~10-20 min  ^<-- run this first
echo  1 = final still            (1920x1080, 256 spp)
echo  2 = preview animation      (960x540, 241 frames)
echo  3 = fast final animation   (1920x1080, 64 spp + denoise, 241 frames)  recommended
echo  4 = full final animation   (1920x1080, 256 spp, 241 frames)  slowest
echo.
set /p CHOICE=Choose 0/1/2/3/4: 

set "SPEC=examples\foggy_cabin_cloud_descent.json"
if "%CHOICE%"=="0" call :speedtest
if "%CHOICE%"=="1" call :speedtest
"%BLENDER%" -b --factory-startup -P tools\build.py -- --spec %SPEC% --quality final_fast --step 24 --out out\desktop_speedtest > out_speedtest.log 2>&1
echo speed test finished. Seconds per frame are in out_speedtest.log ("s/frame") - send me that line.
exit /b 0

:fast
"%BLENDER%" -b --factory-startup -P tools\build.py -- --spec %SPEC% --quality final_fast --out out\desktop_final_fast > out_fast.log 2>&1
echo fast final animation finished (log: out_fast.log)
exit /b 0

:still
if "%CHOICE%"=="2" call :preview
if "%CHOICE%"=="3" call :fast
if "%CHOICE%"=="4" call :final
echo.
echo Done. Results are in the "out" folder. Send me the out\*\manifest.json files too.
pause
exit /b 0

:still
"%BLENDER%" -b --factory-startup -P tools\build.py -- --spec %SPEC% --quality final --still-only --out out\desktop_final_still > out_still.log 2>&1
echo still finished (log: out_still.log)
exit /b 0

:preview
"%BLENDER%" -b --factory-startup -P tools\build.py -- --spec %SPEC% --quality preview --out out\desktop_preview > out_preview.log 2>&1
echo preview animation finished (log: out_preview.log)
exit /b 0

:final
"%BLENDER%" -b --factory-startup -P tools\build.py -- --spec %SPEC% --quality final --out out\desktop_final > out_final.log 2>&1
echo final animation finished (log: out_final.log)
exit /b 0
