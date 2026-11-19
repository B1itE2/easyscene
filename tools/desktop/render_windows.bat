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
echo  1 = final still            (1920x1080, ~2-6 min)
echo  2 = preview animation      (960x540, 241 frames, ~20-40 min)
echo  3 = final animation        (1920x1080, 241 frames, several hours - overnight)
echo  4 = 1 + 2 + 3 in a row
echo.
set /p CHOICE=Choose 1/2/3/4: 

set "SPEC=examples\foggy_cabin_cloud_descent.json"
if "%CHOICE%"=="1" call :still
if "%CHOICE%"=="2" call :preview
if "%CHOICE%"=="3" call :final
if "%CHOICE%"=="4" (call :still & call :preview & call :final)
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
