@echo off
REM Euro Drive Planner - start the local web app at http://localhost:8000
cd /d "%~dp0"
if not exist "frontend\dist\index.html" (
  echo Building the frontend...
  pushd frontend
  call npm install --no-audit --no-fund
  call npm run build
  popd
)
start "" http://localhost:8000
".venv\Scripts\python.exe" backend\run.py --port 8000
