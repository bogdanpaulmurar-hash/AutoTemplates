@echo off
setlocal
cd /d "%~dp0"
echo.
echo  AutoTemplates - instalare / install
echo  Fara drepturi de administrator. Totul se instaleaza doar pentru utilizatorul curent.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -Autostart -DesktopShortcut
if errorlevel 1 goto failed
echo.
echo  ============================================================
echo   Gata! AutoTemplates este instalat si pornit.
echo   - Apasa Ctrl+Q oriunde scrii ca sa alegi un template.
echo   - Iconita e in tray, langa ceas (sageata ^^ daca nu o vezi).
echo   - Porneste singur odata cu Windows. Start / Desktop: AutoTemplates.
echo   - Dezinstalare: Uninstall.bat
echo  ============================================================
goto end
:failed
echo.
echo  Instalarea NU a reusit. Mesajul de eroare este mai sus.
:end
echo.
pause
