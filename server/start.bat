@echo off
rem KCar multiplayer server (local). Needs Node.js 18+.
rem Extra options are passed through, e.g.:  start.bat --port 9000
cd /d "%~dp0.."
where node >nul 2>nul || (echo Node.js not found. Install it from https://nodejs.org/ & pause & exit /b 1)
node server\server.mjs %*
pause
