@echo off
rem Start the bot detached from whatever shell launched it.
rem
rem Launching `python -m app.main` from an agent session or a terminal makes
rem the bot a child of that session: when the session ends, Windows kills the
rem whole process tree and the bot dies with it - ten times in a row, always
rem right after "Run polling" and never reaching the "Bot stopped" line it
rem writes on a clean shutdown.
rem
rem Run this through `start ""` or Task Scheduler and the bot outlives the
rem thing that started it.
cd /d "%~dp0"
.venv\Scripts\python.exe -m app.main >> bot_run.log 2>&1
