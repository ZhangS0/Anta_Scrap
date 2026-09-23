@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ===== Anta_Scrap 版本检查（只读，不修改任何文件）=====
python scripts\update.py check
echo.
pause
