@echo off
set PY_CMD=
py --version >nul 2>&1 && set PY_CMD=py
if not defined PY_CMD python --version >nul 2>&1 && set PY_CMD=python
if not defined PY_CMD (
    echo Python not found. Install Python 3.8+ and check "Add to PATH"
    pause
    exit /b 1
)
%PY_CMD% -c "__import__('subprocess').check_call([__import__('sys').executable,'-m','pip','install','-r','requirements.txt','--quiet'],stdout=__import__('subprocess').DEVNULL,stderr=__import__('subprocess').DEVNULL)"
%PY_CMD% main.py
pause