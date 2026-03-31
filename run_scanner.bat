@echo off
echo Starting HP LaserJet MFP Scanner...
echo.
python scanner.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Scanner failed to start!
    echo Make sure you ran install_drivers.bat first.
    echo.
    pause
)
