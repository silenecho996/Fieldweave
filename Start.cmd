@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "PYTHONUTF8=1"

py -3 -c "import sqlite3, sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto try_python
py -3 -B src\app.py --open %*
goto finish

:try_python
python -c "import sqlite3, sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto try_bundled
python -B src\app.py --open %*
goto finish

:try_bundled
for /f "usebackq delims=" %%P in (
    `powershell.exe -NoProfile -Command "Get-AppxPackage -Name 'OpenAI.CodexPrimaryRuntime*' | Sort-Object Version -Descending | Select-Object -First 1 -ExpandProperty InstallLocation"`
) do if exist "%%P\dependencies\python\python.exe" (
    "%%P\dependencies\python\python.exe" -B src\app.py --open %*
    goto finish
)
echo Python 3.10 or newer is required.
set "research_exit=1"
goto leave

:finish
set "research_exit=%ERRORLEVEL%"

:leave
popd
if not "%research_exit%"=="0" pause
exit /b %research_exit%
