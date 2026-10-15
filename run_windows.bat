@echo off
setlocal
cd /d "%~dp0"
echo.
echo  BAAGH - Kashmir Orchard Marketplace
 echo ================================
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating Python virtual environment...
  py -m venv .venv
  if errorlevel 1 goto error
)
echo [2/3] Installing or updating required packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo [3/3] Starting Baagh at http://127.0.0.1:8000
 echo Press CTRL+C in this window to stop the server.
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto error
goto end
:error
echo.
echo Baagh could not start. Please check the error above and confirm Python 3.10+ is installed.
pause
:end
endlocal
