"""
Tello Scratch ドローンショー・コントローラー

Scratchプロジェクトから生成されたタイムラインに基づいて
Telloドローンのショーを制御するアプリケーションです。

使い方:
    python main.py
"""

import sys
import tkinter as tk

from gui import TelloApp


def setup_dpi_awareness():
    """Windows環境でDPI認識を設定"""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def main():
    """アプリケーションのエントリーポイント"""
    # DPI設定
    setup_dpi_awareness()

    # メインウィンドウ作成
    root = tk.Tk()
    app = TelloApp(root)

    # 終了処理を登録
    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    # メインループ開始
    root.mainloop()


if __name__ == "__main__":
    main()
