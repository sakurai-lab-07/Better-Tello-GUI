"""
Tello Scratch ドローンショー・コントローラー
メインエントリーポイント
"""

import sys
import os
import tkinter as tk

# srcディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import TelloApp


def main():
    """アプリケーションのメインエントリーポイント"""
    # Windows環境でのDPI対応
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    # メインウィンドウの作成
    root = tk.Tk()
    app = TelloApp(root)

    # ウィンドウ終了時の処理
    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    # メインループ
    root.mainloop()


if __name__ == "__main__":
    main()
