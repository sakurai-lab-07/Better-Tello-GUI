"""
設定・環境チェックウィンドウ
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import importlib.util
import subprocess
import sys
import threading


class SettingsWindow:
    """設定・環境チェックウィンドウクラス"""

    def __init__(self, parent):
        self.parent = parent
        self.window = ttk.Toplevel(parent)
        self.window.title("設定・環境チェック")
        self.window.geometry("500x600")
        self.window.minsize(400, 500)

        # 必要なパッケージリスト
        self.required_packages = {
            "ttkbootstrap": "UIフレームワーク",
            "pygame": "音声再生エンジン",
            "librosa": "音声解析（波形表示）",
            "numpy": "数値計算（波形表示）",
        }

        self.package_status = {}

        self._create_widgets()
        self.check_environment()

    def _create_widgets(self):
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)

        # タイトル
        ttk.Label(
            main_frame, text="環境チェック", font=("Yu Gothic UI", 14, "bold")
        ).pack(anchor=W, pady=(0, 10))

        # パッケージリスト用フレーム
        self.pkg_frame = ttk.Labelframe(
            main_frame, text="必須パッケージのステータス", padding=10
        )
        self.pkg_frame.pack(fill=X, pady=(0, 20))

        self.pkg_labels = {}
        for pkg, desc in self.required_packages.items():
            row = ttk.Frame(self.pkg_frame)
            row.pack(fill=X, pady=5)

            ttk.Label(row, text=f"{pkg} ({desc})", width=30).pack(side=LEFT)
            status_label = ttk.Label(
                row, text="確認中...", font=("Yu Gothic UI", 10, "bold")
            )
            status_label.pack(side=RIGHT)
            self.pkg_labels[pkg] = status_label

        # 操作ボタン
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X, pady=10)

        self.recheck_btn = ttk.Button(
            btn_frame,
            text="🔄 再チェック",
            command=self.check_environment,
            bootstyle="secondary-outline",
        )
        self.recheck_btn.pack(side=LEFT, padx=5)

        self.install_btn = ttk.Button(
            btn_frame,
            text="📦 不足パッケージをインストール",
            command=self.install_missing_packages,
            bootstyle="primary",
            state="disabled",
        )
        self.install_btn.pack(side=LEFT, padx=5)

        # ログ表示
        ttk.Label(main_frame, text="実行ログ:", font=("Yu Gothic UI", 10, "bold")).pack(
            anchor=W, pady=(10, 5)
        )
        self.log_text = tk.Text(
            main_frame, height=10, font=("Consolas", 9), state="disabled"
        )
        self.log_text.pack(fill=BOTH, expand=YES)

        # 閉じるボタン
        ttk.Button(
            main_frame,
            text="閉じる",
            command=self.window.destroy,
            bootstyle="secondary",
        ).pack(pady=(20, 0))

    def log(self, message):
        if not self.window.winfo_exists():
            return
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def check_environment(self):
        """パッケージのインストール状況をチェック"""
        if not self.window.winfo_exists():
            return
        self.log("環境チェックを開始します...")
        missing = []
        for pkg in self.required_packages:
            spec = importlib.util.find_spec(pkg)
            if spec is not None:
                self.pkg_labels[pkg].config(
                    text="✅ インストール済み", foreground="green"
                )
                self.package_status[pkg] = True
            else:
                self.pkg_labels[pkg].config(text="❌ 未インストール", foreground="red")
                self.package_status[pkg] = False
                missing.append(pkg)

        if missing:
            self.log(f"不足しているパッケージ: {', '.join(missing)}")
            self.install_btn.config(state="normal")
        else:
            self.log("すべての必須パッケージがインストールされています。")
            self.install_btn.config(state="disabled")

    def install_missing_packages(self):
        """不足しているパッケージをインストール"""
        missing = [
            pkg for pkg, installed in self.package_status.items() if not installed
        ]
        if not missing:
            return

        self.install_btn.config(state="disabled")
        self.recheck_btn.config(state="disabled")

        def run_install():
            self.log(f"インストールを開始します: {', '.join(missing)}")
            try:
                # 仮想環境のpythonを使用
                python_exe = sys.executable
                process = subprocess.Popen(
                    [python_exe, "-m", "pip", "install"] + missing,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    ),
                )

                for line in process.stdout:
                    if not self.window.winfo_exists():
                        break
                    self.log(line.strip())

                process.wait()
                if self.window.winfo_exists():
                    if process.returncode == 0:
                        self.log("インストールが完了しました。")
                    else:
                        self.log(
                            f"エラーが発生しました (終了コード: {process.returncode})"
                        )
            except Exception as e:
                if self.window.winfo_exists():
                    self.log(f"例外が発生しました: {str(e)}")
            finally:
                if self.window.winfo_exists():
                    self.window.after(0, self.check_environment)
                    self.window.after(
                        0, lambda: self.recheck_btn.config(state="normal")
                    )

        threading.Thread(target=run_install, daemon=True).start()
