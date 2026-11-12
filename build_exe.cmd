@echo off
setlocal
rem Сборка "AI Limits.exe" в папку на уровень выше этого скрипта (рядом с папкой Source_code).
rem Пути относительные - папку проекта можно переносить куда угодно.
rem Нужен PyInstaller:  python -m pip install --user pyinstaller

set "SRC=%~dp0"
set "SRC=%SRC:~0,-1%"
cd /d "%SRC%"
for %%I in ("%SRC%\..") do set "OUT=%%~fI"
set "EXE=%OUT%\AI Limits.exe"
set "TMPBUILD=%TEMP%\ai-limits-build"

echo Проверки (окно программы откроется на несколько секунд)...
python "%SRC%\tests\run_tests.py"
if errorlevel 1 (
  echo ОШИБКА: проверки не прошли, сборка отменена.
  goto :end
)

if exist "%EXE%" (
  echo Файл уже существует: "%EXE%"
  choice /C YN /M "Перезаписать"
  if errorlevel 2 (
    echo Сборка отменена.
    goto :end
  )
  tasklist /FI "IMAGENAME eq AI Limits.exe" | find /I "AI Limits.exe" >nul
  if not errorlevel 1 (
    echo AI Limits.exe сейчас запущен.
    choice /C YN /M "Закрыть его и продолжить"
    if errorlevel 2 (
      echo Сборка отменена.
      goto :end
    )
    taskkill /IM "AI Limits.exe" /F >nul
    timeout /t 1 /nobreak >nul
  )
)

echo Сборка...
if not exist "%TMPBUILD%" mkdir "%TMPBUILD%"
python "%SRC%\version.py" "%TMPBUILD%\version_info.txt"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "AI Limits" ^
  --version-file "%TMPBUILD%\version_info.txt" ^
  --icon "%SRC%\ai_limits.ico" --paths "%SRC%" --hidden-import tray --hidden-import limits ^
  --hidden-import storage --hidden-import winapi --hidden-import cloud --hidden-import ide_local --hidden-import ide_switch ^
  --hidden-import ui_theme --hidden-import ui_cards --hidden-import ui_popups --hidden-import ui_tray --hidden-import autostart --hidden-import ui_history --hidden-import history --hidden-import i18n ^
  --distpath "%TMPBUILD%\dist" --workpath "%TMPBUILD%\work" --specpath "%TMPBUILD%" ^
  "%SRC%\limits_gui.pyw"
if errorlevel 1 (
  echo ОШИБКА сборки, старый exe не тронут.
  goto :end
)

copy /Y "%TMPBUILD%\dist\AI Limits.exe" "%EXE%" >nul
if errorlevel 1 (
  echo Не удалось записать "%EXE%" - возможно, программа ещё запущена.
  goto :end
)
python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest() + '  AI Limits.exe')" "%EXE%" > "%EXE%.sha256"
echo Готово: "%EXE%"
echo Контрольная сумма SHA-256: "%EXE%.sha256"

:end
endlocal
pause
