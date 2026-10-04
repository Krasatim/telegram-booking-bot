@echo off
rem Запуск бота. Остановить: закрыть это окно или нажать Ctrl+C
cd /d "%~dp0"
.venv\Scripts\python.exe -m bot
pause
