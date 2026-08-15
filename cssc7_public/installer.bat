@echo off
setlocal enabledelayedexpansion
set "HERE=%~dp0"
set "PYEXE="

REM 1) bundled embeddable Python 3.12 (fully offline)
if exist "%HERE%python\python.exe" set "PYEXE="%HERE%python\python.exe""

REM 2) a system Python that is exactly 3.12
if not defined PYEXE (
  for /f "delims=" %%p in ('where python 2^>nul') do (
    if not defined PYEXE (
      "%%p" -c "import sys;raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1 && set "PYEXE="%%p""
    )
  )
)

REM 3) the py launcher's 3.12
if not defined PYEXE (
  py -3.12 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.12"
)

if not defined PYEXE (
  echo.
  echo   Python 3.12 was not found and no bundled runtime is present.
  echo   Install Python 3.12 from https://www.python.org/downloads/ and re-run
  echo   this installer.
  echo.
  pause
  exit /b 1
)

echo Using Python: %PYEXE%
echo.
%PYEXE% "%HERE%installer.py" %*
echo.
pause
