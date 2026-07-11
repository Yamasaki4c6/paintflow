@echo off
chcp 65001 > nul
cd /d %~dp0
echo ============================================
echo  Paintflow Studio - exe ビルド
echo  (初回は5〜10分かかります)
echo ============================================
python -m pip install --upgrade pyinstaller
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --windowed --name PaintflowStudio ^
  --icon assets\icon.ico ^
  --exclude-module PySide6.QtWebEngineCore ^
  --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.QtMultimedia ^
  studio_main.py
echo.
echo ============================================
echo  完成: dist\PaintflowStudio\PaintflowStudio.exe
echo  (dist\PaintflowStudio フォルダごと移動・配布できます)
echo ============================================
pause
