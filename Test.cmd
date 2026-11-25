@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "PYTHONUTF8=1"
py -3 -B -m unittest discover -s tests -v
set "research_exit=%ERRORLEVEL%"
popd
pause
exit /b %research_exit%
