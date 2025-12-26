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
from ttkbootstrap.widgets.scrolled import ScrolledFrame


class SettingsWindow:
    """設定・環境チェックウィンドウクラス"""

    def __init__(self, parent, app_instance=None):
        self.parent = parent
        self.app_instance = app_instance
        self.window = ttk.Toplevel(parent)
        self.window.title("設定・環境チェック")
        # ウィンドウサイズの設定
        self.window.geometry("580x710")
        self.window.minsize(580, 710)

        # 必要なパッケージリスト
        self.required_packages = {
            "ttkbootstrap": "UIフレームワーク",
            "pygame": "音声再生エンジン",
            "librosa": "音声解析（波形表示）",
            "numpy": "数値計算（波形表示）",
        }

        self.package_status = {}

        self._create_widgets()

        # UIの描画を強制
        self.window.update()
        self.window.lift()
        self.window.focus_force()

        # 設定ウィンドウ呼び出しで環境チェックを自動実行
        self.check_environment()

    def _create_widgets(self):
        # メインフレーム
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)

        # --- 外観設定 ---
        ttk.Label(main_frame, text="外観設定", font=("Yu Gothic UI", 12, "bold")).pack(
            anchor=W, pady=(10, 10)
        )

        theme_frame = ttk.Labelframe(main_frame, text="テーマ設定", padding=10)
        theme_frame.pack(fill=X, pady=(0, 20), padx=20)

        # テーマ名の取得を安全にする
        current_theme = "cosmo"
        try:
            current_theme = self.parent.style.theme_use()
        except:
            pass

        self.theme_var = tk.StringVar(value=current_theme)

        light_radio = ttk.Radiobutton(
            theme_frame,
            text="ライトモード (cosmo)",
            variable=self.theme_var,
            value="cosmo",
            command=self._on_theme_change,
        )
        light_radio.pack(side=LEFT, padx=20)

        dark_radio = ttk.Radiobutton(
            theme_frame,
            text="ダークモード (darkly)",
            variable=self.theme_var,
            value="darkly",
            command=self._on_theme_change,
        )
        dark_radio.pack(side=LEFT, padx=20)

        # --- 環境チェック ---
        ttk.Label(
            main_frame, text="環境チェック", font=("Yu Gothic UI", 12, "bold")
        ).pack(anchor=W, pady=(0, 10), padx=20)

        # パッケージリスト用フレーム
        self.pkg_frame = ttk.Labelframe(
            main_frame, text="必須パッケージのステータス", padding=10
        )
        self.pkg_frame.pack(fill=X, pady=(0, 20), padx=20)

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
        btn_frame.pack(fill=X, pady=10, padx=20)

        self.recheck_btn = ttk.Button(
            btn_frame,
            text="🔄 再チェック",
            command=self.check_environment,
            bootstyle="secondary",
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
            anchor=W, pady=(10, 5), padx=20
        )
        colors = self.parent.style.colors
        self.log_text = tk.Text(
            main_frame,
            height=10,
            font=("Consolas", 11),
            state="disabled",
            bg=colors.inputbg,
            fg=colors.inputfg,
            insertbackground=colors.inputfg,
        )
        self.log_text.pack(fill=X, pady=(0, 10), padx=20)

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
        colors = self.parent.style.colors
        for pkg in self.required_packages:
            spec = importlib.util.find_spec(pkg)
            if spec is not None:
                self.pkg_labels[pkg].config(
                    text="✅ インストール済み", foreground=colors.success
                )
                self.package_status[pkg] = True
            else:
                self.pkg_labels[pkg].config(
                    text="❌ 未インストール", foreground=colors.danger
                )
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

    def _on_theme_change(self):
        """テーマが変更された時の処理"""
        new_theme = self.theme_var.get()
        self.log(f"テーマを {new_theme} に変更します...")

        if self.app_instance:
            self.app_instance.change_theme(new_theme)
        else:
            # app_instanceがない場合は直接スタイルを変更
            self.parent.style.theme_use(new_theme)

        # 自身のログテキストの色も更新
        colors = self.parent.style.colors
        self.log_text.configure(
            bg=colors.inputbg, fg=colors.inputfg, insertbackground=colors.inputfg
        )
