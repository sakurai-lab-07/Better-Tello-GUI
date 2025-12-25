"""
Tello Scratchドローンショー・コントローラー
メインエントリーポイント
"""

import sys
import os
import ttkbootstrap as tb

# Tcl/Tkのパスを明示的に設定（Windowsの仮想環境でのTclError対策）
if sys.platform == "win32":
    base_python = sys.base_prefix
    tcl_path = os.path.join(base_python, "tcl", "tcl8.6")
    tk_path = os.path.join(base_python, "tcl", "tk8.6")

    if os.path.exists(tcl_path):
        os.environ["TCL_LIBRARY"] = tcl_path
    if os.path.exists(tk_path):
        os.environ["TK_LIBRARY"] = tk_path

# DPI対応（Windows）
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# GUI起動
from gui import TelloApp
from config import CONFIG_FILE
import json


def main():
    """アプリケーションのメイン関数"""
    # 設定ファイルからテーマを読み込む
    theme = "cosmo"
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                theme = config.get("app_theme", "cosmo")
        except:
            pass

    # ttkbootstrapのWindowを使用（テーマを指定可能）
    root = tb.Window(themename=theme)
    app = TelloApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
