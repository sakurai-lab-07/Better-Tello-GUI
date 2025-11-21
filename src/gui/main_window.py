"""
メインGUIウィンドウ
"""

import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from queue import Queue

from config import (
    CONFIG_FILE,
    FONT_NORMAL,
    FONT_BOLD_LARGE,
    FONT_HEADER,
    FONT_MONOSPACE,
)
from config import COLOR_BACKGROUND, COLOR_ACCENT, COLOR_ACCENT_HOVER
from config import (
    COLOR_STOP,
    COLOR_STOP_HOVER,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_HIGHLIGHT,
)
from scratch_parser import ScratchProjectParser
from show_runner import run_show_worker


class TelloApp:
    """メインGUIアプリケーションクラス"""

    def __init__(self, master):
        """アプリケーションの初期化"""
        self.master = master
        self.master.title("Tello Scratch ドローンショー・コントローラー")
        self.master.geometry("900x650")
        self.master.minsize(800, 500)
        self.master.configure(bg=COLOR_BACKGROUND)

        # フォント設定
        self.font_normal = FONT_NORMAL
        self.font_bold_large = FONT_BOLD_LARGE
        self.font_header = FONT_HEADER
        self.font_monospace = FONT_MONOSPACE

        # スタイル設定
        self._configure_styles()

        # 状態変数の初期化
        self.drone_entry_widgets = []
        self.schedule = None
        self.total_time = 0.0
        self.time_to_line_map = {}
        self.last_highlighted_lines = None
        self.sb3_path = tk.StringVar()
        self.show_status = tk.StringVar(value="準備完了")
        self.log_queue = Queue()
        self.show_thread = None
        self.stop_event = threading.Event()

        # UI構築と初期化
        self._create_widgets()
        self.load_config()
        self.process_log_queue()

    def _configure_styles(self):
        """UI要素のスタイルを設定"""
        s = ttk.Style()
        s.theme_use("clam")

        # 基本スタイル
        s.configure("TFrame", background=COLOR_BACKGROUND)
        s.configure(
            "TLabel",
            background=COLOR_BACKGROUND,
            foreground="black",
            font=self.font_normal,
        )
        s.configure("Header.TLabel", font=self.font_header, foreground=COLOR_ACCENT)

        # LabelFrame
        s.configure("TLabelframe", background=COLOR_BACKGROUND)
        s.configure("TLabelframe.Label", font=self.font_bold_large, foreground="#333")

        # ボタン
        s.configure("TButton", font=self.font_normal, padding=6)
        s.configure(
            "Accent.TButton",
            font=self.font_normal,
            padding=8,
            foreground="white",
            background=COLOR_ACCENT,
        )
        s.map("Accent.TButton", background=[("active", COLOR_ACCENT_HOVER)])
        s.configure(
            "Stop.TButton",
            font=self.font_normal,
            padding=8,
            foreground="white",
            background=COLOR_STOP,
        )
        s.map("Stop.TButton", background=[("active", COLOR_STOP_HOVER)])

    def _create_widgets(self):
        """UI要素を作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.master, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)

        # 左側パネル
        self._create_left_panel(main_frame)

        # 右側パネル（ログとタイムライン）
        self._create_right_panel(main_frame)

    def _create_left_panel(self, parent):
        """左側パネルを作成"""
        left_frame = ttk.Frame(parent)
        left_frame.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 15))
        left_frame.grid_rowconfigure(2, weight=1)

        # ① ドローン設定
        self._create_drone_config_section(left_frame)

        # ② プロジェクト選択
        self._create_file_selection_section(left_frame)

        # ③ ショー実行
        self._create_action_section(left_frame)

    def _create_drone_config_section(self, parent):
        """ドローン設定セクションを作成"""
        ip_frame = ttk.LabelFrame(parent, text="① ドローンの設定", padding="10")
        ip_frame.pack(fill="x", pady=(0, 15))

        self.ip_entry_frame = ttk.Frame(ip_frame)
        self.ip_entry_frame.pack(fill="x")

        # ボタンフレーム
        ip_button_frame = ttk.Frame(ip_frame)
        ip_button_frame.pack(fill="x", pady=(10, 5))

        ttk.Button(ip_button_frame, text="＋ 追加", command=self.add_drone_entry).pack(
            side="left", expand=True, fill="x", padx=(0, 2)
        )

        ttk.Button(
            ip_button_frame, text="－ 削除", command=self.remove_drone_entry
        ).pack(side="left", expand=True, fill="x", padx=(2, 0))

        ttk.Button(ip_frame, text="⚙️ 設定を保存", command=self.save_config).pack(
            fill="x", pady=(10, 0)
        )

    def _create_file_selection_section(self, parent):
        """プロジェクト選択セクションを作成"""
        file_frame = ttk.LabelFrame(parent, text="② プロジェクト選択", padding="10")
        file_frame.pack(fill="x", pady=(0, 15))

        self.sb3_path_label = ttk.Label(
            file_frame, text="ファイルが選択されていません", wraplength=230
        )
        self.sb3_path_label.pack(fill="x", pady=(0, 10))

        ttk.Button(
            file_frame, text="📂 Scratchファイルを開く", command=self.select_file
        ).pack(fill="x")

    def _create_action_section(self, parent):
        """ショー実行セクションを作成"""
        action_frame = ttk.LabelFrame(parent, text="③ ショー実行", padding="10")
        action_frame.pack(fill="x")

        self.parse_btn = ttk.Button(
            action_frame,
            text="🔄 タイムラインを解析",
            command=self.parse_scratch_project,
            state="disabled",
        )
        self.parse_btn.pack(fill="x", pady=(0, 5))

        self.start_btn = ttk.Button(
            action_frame,
            text="▶️ ショーを開始",
            command=self.start_show,
            state="disabled",
            style="Accent.TButton",
        )
        self.start_btn.pack(fill="x", pady=(5, 5))

        self.stop_btn = ttk.Button(
            action_frame,
            text="⏹️ 緊急停止",
            command=self.emergency_stop,
            state="disabled",
            style="Stop.TButton",
        )
        self.stop_btn.pack(fill="x", pady=(5, 0))

    def _create_right_panel(self, parent):
        """右側パネル（ステータスバー、タイムライン、ログ）を作成"""
        # ステータスバー
        status_bar = ttk.Frame(parent, padding=(5, 5))
        status_bar.grid(row=0, column=1, sticky="ew", pady=(0, 5))

        ttk.Label(status_bar, text="ステータス:", style="Header.TLabel").pack(
            side="left"
        )
        ttk.Label(status_bar, textvariable=self.show_status).pack(side="left", padx=5)

        # ログペイン
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        log_pane = ttk.PanedWindow(right_frame, orient="horizontal")
        log_pane.pack(fill="both", expand=True)

        # タイムラインフレーム
        self._create_timeline_frame(log_pane)

        # 通信ログフレーム
        self._create_log_frame(log_pane)

    def _create_timeline_frame(self, parent):
        """タイムラインフレームを作成"""
        timeline_frame = ttk.Frame(parent, width=400)
        ttk.Label(timeline_frame, text="タイムライン", style="Header.TLabel").pack(
            anchor="w", padx=5
        )

        self.schedule_text = scrolledtext.ScrolledText(
            timeline_frame,
            state="disabled",
            wrap="none",
            height=10,
            font=self.font_monospace,
        )
        self.schedule_text.pack(expand=True, fill="both", padx=5, pady=(0, 5))

        # タグ設定
        self.schedule_text.tag_config("INFO", foreground="black")
        self.schedule_text.tag_config("WAIT", foreground="blue")
        self.schedule_text.tag_config("WARNING", foreground=COLOR_ERROR)
        self.schedule_text.tag_config(
            "HEADER", foreground=COLOR_ACCENT, font=self.font_header
        )
        self.schedule_text.tag_config("HIGHLIGHT", background=COLOR_HIGHLIGHT)

        parent.add(timeline_frame, weight=1)

    def _create_log_frame(self, parent):
        """通信ログフレームを作成"""
        log_frame = ttk.Frame(parent, width=200)
        ttk.Label(log_frame, text="通信ログ", style="Header.TLabel").pack(
            anchor="w", padx=5
        )

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            state="disabled",
            wrap="none",
            height=10,
            font=self.font_monospace,
        )
        self.log_text.pack(expand=True, fill="both", padx=5, pady=(0, 5))

        # タグ設定
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("SUCCESS", foreground=COLOR_SUCCESS)
        self.log_text.tag_config("WARNING", foreground=COLOR_WARNING)
        self.log_text.tag_config("ERROR", foreground=COLOR_ERROR)

        parent.add(log_frame, weight=1)

    # ========================================================================
    # ドローン設定管理
    # ========================================================================

    def add_drone_entry(self, name=None, ip=""):
        """ドローンの設定エントリを追加"""
        drone_count = len(self.drone_entry_widgets)
        if name is None:
            name = f"Tello_{chr(65 + drone_count)}"

        # ウィジェットの作成
        widget_dict = {}
        row_frame = ttk.Frame(self.ip_entry_frame)
        row_frame.pack(fill="x", pady=2)

        label = ttk.Label(row_frame, text=f"{name}:")
        label.pack(side="left", padx=(0, 5))

        entry = ttk.Entry(row_frame)
        entry.pack(side="left", expand=True, fill="x")
        entry.insert(0, ip)

        widget_dict["name"] = name
        widget_dict["frame"] = row_frame
        widget_dict["ip_widget"] = entry
        self.drone_entry_widgets.append(widget_dict)

    def remove_drone_entry(self):
        """最後のドローン設定エントリを削除"""
        if not self.drone_entry_widgets:
            return

        widgets_to_remove = self.drone_entry_widgets.pop()
        widgets_to_remove["frame"].destroy()

    def load_config(self):
        """設定ファイルからドローン設定を読み込む"""
        try:
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)

            # 既存のエントリをクリア
            while self.drone_entry_widgets:
                self.remove_drone_entry()

            # 設定からエントリを追加
            for name, ip in config_data.items():
                self.add_drone_entry(name=name, ip=ip)

            self.log(
                {
                    "level": "INFO",
                    "message": f"{CONFIG_FILE} から設定を読み込みました。",
                }
            )

        except FileNotFoundError:
            self.log(
                {
                    "level": "WARNING",
                    "message": "設定ファイルが見つかりません。ドローンを１台以上IPアドレスを入力し、保存してください。",
                }
            )
            if not self.drone_entry_widgets:
                self.add_drone_entry()

        except Exception as e:
            self.log({"level": "ERROR", "message": f"設定の読み込みエラー: {e}"})

    def save_config(self):
        """ドローン設定をファイルに保存"""
        config_data = {
            widgets["name"]: widgets["ip_widget"].get()
            for widgets in self.drone_entry_widgets
        }

        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config_data, f, indent=4)

            self.log(
                {"level": "INFO", "message": f"{CONFIG_FILE} に設定を保存しました。"}
            )
            messagebox.showinfo("成功", "IPアドレスを保存しました。")

        except Exception as e:
            messagebox.showerror("エラー", f"設定の保存に失敗しました: {e}")

    # ========================================================================
    # ファイル選択とプロジェクト解析
    # ========================================================================

    def select_file(self):
        """Scratchプロジェクトファイルを選択"""
        path = filedialog.askopenfilename(
            title="Scratch 3 プロジェクトファイルを選択",
            filetypes=[("Scratch プロジェクト", "*.sb3")],
        )

        if path:
            self.sb3_path.set(path)
            self.sb3_path_label.configure(text=path.split("/")[-1])
            self.parse_btn["state"] = "normal"
            self.log({"level": "INFO", "message": f"選択されたファイル: {path}"})
            self.show_status.set(f"ファイル選択済み: {path.split('/')[-1]}")

    def parse_scratch_project(self):
        """Scratchプロジェクトを解析してタイムラインを生成"""
        path = self.sb3_path.get()
        if not path:
            return

        # テキストエリアをクリア
        for widget in [self.schedule_text, self.log_text]:
            widget.config(state="normal")
            widget.delete(1.0, tk.END)
            widget.config(state="disabled")

        # プロジェクトを解析
        parser = ScratchProjectParser(path, self.log_queue)
        self.schedule, self.total_time = parser.parse_to_schedule()

        # タイムラインを表示
        self._display_timeline(parser)

    def _display_timeline(self, parser):
        """タイムラインを表示"""
        self.schedule_text.config(state="normal")
        self.schedule_text.delete(1.0, tk.END)
        self.time_to_line_map = {}

        if self.schedule or parser.has_any_valid_action:
            # ヘッダー
            self.schedule_text.insert(
                tk.END,
                f"--- 生成されたタイムライン (予想総時間: {self.total_time:.2f}秒) ---\n\n",
                "HEADER",
            )
            current_line = 3

            # イベントを時刻ごとにグループ化
            grouped_events = {}
            for event in self.schedule:
                if event["time"] not in grouped_events:
                    grouped_events[event["time"]] = []
                grouped_events[event["time"]].append(event)

            # イベントを表示
            for time, events in sorted(grouped_events.items()):
                start_line = current_line

                for event in events:
                    evt_type = event.get("type", "COMMAND")

                    if evt_type == "COMMAND":
                        log_msg = f"{time: >6.2f}s | {event.get('target', 'N/A'): <8} | 実行: {event.get('command', '')}\n"
                        self.schedule_text.insert(tk.END, log_msg, "INFO")

                    elif evt_type == "WAIT":
                        log_msg = f"{time: >6.2f}s | {event.get('target', 'N/A'): <8} | 待機: {event.get('text', '')}\n"
                        self.schedule_text.insert(tk.END, log_msg, "WAIT")

                    elif evt_type == "WARNING":
                        log_msg = f"{time: >6.2f}s | {event.get('text', '')}\n"
                        self.schedule_text.insert(tk.END, log_msg, "WARNING")

                    current_line += 1

                end_line = current_line - 1
                self.time_to_line_map[time] = {"start": start_line, "end": end_line}

            self.log(
                {
                    "level": "INFO",
                    "message": "解析に成功しました。ショーを開始できます。",
                }
            )
            self.start_btn["state"] = "normal"
            self.show_status.set(f"解析完了 (予想時間: {self.total_time:.2f}秒)")

        else:
            self.schedule_text.insert(
                tk.END,
                "ファイルから有効なスケジュールを生成できませんでした。\n",
                "ERROR",
            )
            self.schedule_text.insert(
                tk.END,
                "ヒント: スプライトに「緑の旗が押されたとき」ブロックがありますか？\n",
                "INFO",
            )
            self.show_status.set("解析失敗")

        self.schedule_text.config(state="disabled")

    # ========================================================================
    # ショー実行制御
    # ========================================================================

    def start_show(self):
        """ドローンショーを開始"""
        drones_config = [
            {"name": w["name"], "pc_ip": w["ip_widget"].get()}
            for w in self.drone_entry_widgets
        ]

        if not all(c["pc_ip"] for c in drones_config):
            messagebox.showerror(
                "エラー", "開始前に、すべてのIPアドレスを入力してください。"
            )
            return

        # UIの状態を更新
        self.start_btn["state"] = "disabled"
        self.parse_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"
        self.stop_event.clear()
        self.show_status.set("ショー実行中...")

        # ショーを別スレッドで実行
        self.show_thread = threading.Thread(
            target=run_show_worker,
            args=(
                drones_config,
                self.schedule,
                self.stop_event,
                self.log_queue,
                self.total_time,
            ),
        )
        self.show_thread.start()

    def emergency_stop(self):
        """緊急停止"""
        self.log(
            {
                "level": "ERROR",
                "message": "\n!!! ユーザーによる緊急停止が要求されました !!!",
            }
        )
        self.stop_event.set()

        # UIの状態を更新
        self.stop_btn["state"] = "disabled"
        self.start_btn["state"] = "normal"
        self.parse_btn["state"] = "normal"
        self.show_status.set("緊急停止 - 着陸中")

    # ========================================================================
    # ログとUI更新
    # ========================================================================

    def log(self, log_item):
        """ログをキューに追加"""
        self.log_queue.put(log_item)

    def process_log_queue(self):
        """ログキューを処理してUIを更新"""
        try:
            while not self.log_queue.empty():
                log_item = self.log_queue.get_nowait()

                # 特殊なコマンド
                if isinstance(log_item, dict) and "type" in log_item:
                    if log_item["type"] == "highlight":
                        self.update_timeline_highlight(log_item.get("time"))
                        continue
                    elif log_item["type"] == "clear_highlight":
                        self.update_timeline_highlight(None)
                        continue

                # 通常のログ
                if isinstance(log_item, dict):
                    level = log_item.get("level", "INFO")
                    message = log_item.get("message", "")
                else:
                    level = "INFO"
                    message = str(log_item)

                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, message + "\n", level)
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")

        finally:
            self.master.after(100, self.process_log_queue)

    def update_timeline_highlight(self, current_time):
        """タイムラインのハイライトを更新"""
        self.schedule_text.config(state="normal")

        # 前回のハイライトをクリア
        if self.last_highlighted_lines:
            self.schedule_text.tag_remove(
                "HIGHLIGHT",
                f"{self.last_highlighted_lines['start']}.0",
                f"{self.last_highlighted_lines['end']}.end",
            )
            self.last_highlighted_lines = None

        # 新しい行をハイライト
        if current_time is not None and current_time in self.time_to_line_map:
            line_info = self.time_to_line_map[current_time]
            self.schedule_text.tag_add(
                "HIGHLIGHT", f"{line_info['start']}.0", f"{line_info['end']}.end"
            )
            self.schedule_text.see(f"{line_info['start']}.0")
            self.last_highlighted_lines = line_info

        self.schedule_text.config(state="disabled")

    def on_closing(self):
        """ウィンドウが閉じられる時の処理"""
        if self.show_thread and self.show_thread.is_alive():
            if messagebox.askyesno(
                "終了確認", "ショーが実行中です。停止して終了しますか？"
            ):
                self.emergency_stop()
                self.master.destroy()
        else:
            self.master.destroy()
