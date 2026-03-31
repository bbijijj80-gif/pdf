@echo off
chcp 65001 >nul
echo ============================================
echo Установка зависимостей для HP LaserJet Scanner
echo ============================================
echo.

:: Проверка Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ОШИБКА: Python не найден!
    echo Установите Python с https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Обновление pip...
python -m pip install --upgrade pip --quiet

echo [2/3] Установка comtypes (для работы со сканером WIA)...
pip install comtypes --quiet

echo [3/3] Установка Pillow (для обработки изображений)...
pip install Pillow --quiet

echo.
echo ============================================
echo Установка завершена успешно!
echo ============================================
echo.
echo Запустите scanner.py для начала работы:
echo   python scanner.py
echo.
pause
