@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

REM スクリプトの場所をカレントディレクトリにする
cd /d %~dp0

echo ==================================================
echo   Better-Tello-GUI EXE Build Script
echo ==================================================

REM 1. 仮想環境の確認と有効化
echo [1/4] Checking environment...
if exist ".venv\Scripts\activate.bat" (
    echo Virtual environment found. Activating...
    call ".venv\Scripts\activate.bat"
) else (
    echo Virtual environment not found. Using system Python...
)

REM 2. 必要なライブラリのインストール/更新
echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
pip install pyinstaller ttkbootstrap pillow pygame librosa numpy scipy

REM 3. PyInstallerによるビルド
echo [3/4] Creating EXE (This may take a few minutes)...

REM Pythonのインストールパスを取得
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.base_prefix)"') do set PY_PATH=%%i

REM Tcl/Tkのパスを明示的に設定
set TCL_ROOT=%PY_PATH%\tcl
set DLL_DIR=%PY_PATH%\DLLs
set LIB_DIR=%PY_PATH%\Lib
set TK_PKG_DIR=%PY_PATH%\Lib\tkinter

echo Using Python at: %PY_PATH%

pyinstaller --onefile --noconsole ^
    --paths "%LIB_DIR%" ^
    --add-data "src/img;img" ^
    --add-data "%TCL_ROOT%;tcl_root" ^
    --add-data "%TK_PKG_DIR%;tkinter" ^
    --add-binary "%DLL_DIR%\tcl86t.dll;." ^
    --add-binary "%DLL_DIR%\tk86t.dll;." ^
    --collect-all ttkbootstrap ^
    --hidden-import tkinter ^
    --hidden-import _tkinter ^
    --name "BetterTelloGUI" ^
    --clean ^
    src/main.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b %ERRORLEVEL%
)

REM 4. 終了処理
echo.
echo [4/4] Finalizing...
if exist "tello_config.json" (
    echo Copying tello_config.json to dist folder...
    if not exist "dist" mkdir "dist"
    copy /y "tello_config.json" "dist\"
)

echo.
echo Build Completed!
echo --------------------------------------------------
echo Output: dist\BetterTelloGUI.exe
echo Note: tello_config.json must be in the same folder as the EXE.
echo --------------------------------------------------
pause
