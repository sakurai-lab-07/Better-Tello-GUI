"""
Tello Scratchドローンショー・コントローラー
メインエントリーポイント
"""

import sys
import tkinter as tk

# DPI対応（Windows）
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# GUI起動
from gui import TelloApp


def main():
    """アプリケーションのメイン関数"""
    root = tk.Tk()
    app = TelloApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
