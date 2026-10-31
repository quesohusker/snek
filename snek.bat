@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto run
echo First run: installing Snek into .venv. This takes a minute.
py -3 -m venv .venv 2>nul || python -m venv .venv
if not exist .venv\Scripts\python.exe goto nopython
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -e .
if errorlevel 1 goto failed
:run
.venv\Scripts\python -m snek %*
goto :eof
:nopython
echo Snek needs Python 3.12 or newer. Get it at https://www.python.org/downloads/
pause
goto :eof
:failed
echo Install failed. Check that Python is 3.12 or newer.
pause
