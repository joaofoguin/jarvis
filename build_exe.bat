@echo off
rem Cria o JARVIS.exe na pasta do projeto. Rode uma vez; depois as atualizacoes chegam pelo Git.
cd /d "%~dp0"
venv\Scripts\python -m pip install -q pyinstaller
set ICON=
if exist "%USERPROFILE%\.jarvis\jarvis.ico" set ICON=--icon "%USERPROFILE%\.jarvis\jarvis.ico"
venv\Scripts\pyinstaller --onefile --noconsole --name JARVIS %ICON% --distpath . --workpath build --specpath build updater.py
echo.
echo Pronto: JARVIS.exe esta na pasta do projeto. Crie um atalho dele na area de trabalho ou em shell:startup.
pause
