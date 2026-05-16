@echo off
echo Сборка AutoDropVideo...
pip install pyinstaller --quiet
pyinstaller AutoDropVideo.spec --clean
echo.
echo Готово! Файл: dist\AutoDropVideo.exe
pause
