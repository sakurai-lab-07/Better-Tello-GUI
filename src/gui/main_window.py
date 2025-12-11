"""
メインウィンドウモジュール

Tello Scratchドローンショーコントローラーのメインウィンドウを提供します。
"""

import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from queue import Queue
import threading

from scratch_parser import ScratchProjectParser
from show_runner import ShowRunner
from music_player import MusicPlayer
from project_manager import ProjectManager
from youtube_downloader import YouTubeDownloader
from core.network_manager import NetworkManager
from config import (
    FONT_NORMAL,
    FONT_BOLD_LARGE,
    FONT_HEADER,
    FONT_MONOSPACE,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_PRIMARY_DISABLED,
    COLOR_DANGER,
    COLOR_DANGER_HOVER,
    COLOR_DANGER_DISABLED,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_BACKGROUND,
    COLOR_TEXT,
    COLOR_HIGHLIGHT,
    WINDOW_TITLE,
    WINDOW_SIZE,
    WINDOW_MIN_SIZE,
    MAIN_PADDING,
    DEFAULT_DRONE_PREFIX,
    CONFIG_FILENAME,
    SUPPORTED_PROJECT_FILES,
    SUPPORTED_AUDIO_FILES,
    LOG_QUEUE_UPDATE_INTERVAL,
    LOG_LEVEL_INFO,
    LOG_LEVEL_SUCCESS,
    LOG_LEVEL_WARNING,
    LOG_LEVEL_ERROR,
    EVENT_TYPE_TAKEOFF,
    EVENT_TYPE_COMMAND,
    EVENT_TYPE_WAIT,
    EVENT_TYPE_WARNING,
    EVENT_TYPE_LAND,
    EVENT_TYPE_INFO,
)


class TelloApp:
    """
    Tello Scratchドローンショーコントローラーのメインアプリケーションクラス
    """

    def __init__(self, master):
        """
        アプリケーションを初期化

        Args:
            master: Tkinterのルートウィンドウ
        """
        self.master = master
        self.master.title(WINDOW_TITLE)
        self.master.geometry(WINDOW_SIZE)
        self.master.minsize(*WINDOW_MIN_SIZE)

        self.setup_styles()

        # 内部状態変数
        self.drone_entry_widgets = []
        self.schedule = None
        self.total_time = 0.0
        self.time_to_line_map = {}
        self.last_highlighted_lines = None
        self.sb3_path = tk.StringVar()
        self.audio_path = tk.StringVar()
        self.show_status = tk.StringVar(value="準備完了")
        self.log_queue = Queue()
        self.show_thread = None
        self.stop_event = threading.Event()
        self.controllers = {}

        # 音楽関連
        self.music_list = []  # メドレー用の音楽リスト
        self.is_medley_mode = False  # メドレーモードかどうか
        self.youtube_titles = {}  # YouTubeタイトルのキャッシュ
        self.bpm_data = {}  # BPM情報のキャッシュ

        # プロジェクト関連
        self.current_project_path = None  # 現在のプロジェクトパス

        # 音楽プレイヤー初期化
        self.music_player = MusicPlayer(log_callback=self.log)

        # プロジェクトマネージャー初期化
        self.project_manager = ProjectManager(log_queue=self.log_queue)

        # YouTubeダウンローダー初期化
        self.youtube_downloader = YouTubeDownloader(log_queue=self.log_queue)

        self._create_widgets()
        self.load_config()
        self.process_log_queue()

    def setup_styles(self):
        """スタイルとテーマを設定"""
        self.font_normal = FONT_NORMAL
        self.font_bold_large = FONT_BOLD_LARGE
        self.font_header = FONT_HEADER
        self.font_monospace = FONT_MONOSPACE

        s = ttk.Style()
        s.theme_use("clam")

        # 基本スタイル
        s.configure(
            ".", background=COLOR_BACKGROUND, foreground="black", font=self.font_normal
        )
        s.configure("TFrame", background=COLOR_BACKGROUND)
        s.configure("TLabel", background=COLOR_BACKGROUND, foreground="black")
        s.configure("Header.TLabel", font=self.font_header, foreground=COLOR_PRIMARY)
        s.configure("TLabelframe", background=COLOR_BACKGROUND)
        s.configure(
            "TLabelframe.Label", font=self.font_bold_large, foreground=COLOR_TEXT
        )
        s.configure("TButton", font=self.font_normal, padding=6)

        # アクセントボタン
        s.configure(
            "Accent.TButton",
            font=self.font_normal,
            padding=8,
            foreground="white",
            background=COLOR_PRIMARY,
        )
        s.map(
            "Accent.TButton",
            background=[
                ("active", COLOR_PRIMARY_HOVER),
                ("disabled", COLOR_PRIMARY_DISABLED),
            ],
        )

        # 停止ボタン
        s.configure(
            "Stop.TButton",
            font=self.font_normal,
            padding=8,
            foreground="white",
            background=COLOR_DANGER,
        )
        s.map(
            "Stop.TButton",
            background=[
                ("active", COLOR_DANGER_HOVER),
                ("disabled", COLOR_DANGER_DISABLED),
            ],
        )

    def _create_widgets(self):
        """すべてのUIウィジェットを作成"""
        main_frame = ttk.Frame(self.master, padding=MAIN_PADDING)
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=0, minsize=250)  # 左パネルの最小幅
        main_frame.grid_columnconfigure(1, weight=1)  # 右パネルが伸縮

        # 左カラム（スクロール可能）
        left_canvas = tk.Canvas(main_frame, bg=COLOR_BACKGROUND, highlightthickness=0)
        left_canvas.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 15))

        left_scrollbar = ttk.Scrollbar(
            main_frame, orient="vertical", command=left_canvas.yview
        )
        left_scrollbar.grid(row=0, column=0, rowspan=2, sticky="nse", padx=(0, 15))

        left_frame = ttk.Frame(left_canvas)
        left_canvas_frame = left_canvas.create_window(
            (0, 0), window=left_frame, anchor="nw"
        )

        def configure_scroll_region(event):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def configure_canvas_width(event):
            canvas_width = event.width
            left_canvas.itemconfig(left_canvas_frame, width=canvas_width)

        left_frame.bind("<Configure>", configure_scroll_region)
        left_canvas.bind("<Configure>", configure_canvas_width)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)

        # マウスホイールでスクロール
        def on_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        left_canvas.bind_all("<MouseWheel>", on_mousewheel)

        self._create_drone_config_section(left_frame)
        self._create_project_selection_section(left_frame)
        self._create_audio_selection_section(left_frame)
        self._create_show_control_section(left_frame)

        # 右カラム
        self._create_status_bar(main_frame)
        self._create_log_panels(main_frame)

    def _create_drone_config_section(self, parent):
        """① ドローン設定セクションを作成"""
        ip_frame = ttk.LabelFrame(parent, text="① ドローンの設定", padding="10")
        ip_frame.pack(fill="x", pady=(0, 15))

        self.ip_entry_frame = ttk.Frame(ip_frame)
        self.ip_entry_frame.pack(fill="x")

        ip_button_frame = ttk.Frame(ip_frame)
        ip_button_frame.pack(fill="x", pady=(10, 5))

        ttk.Button(ip_button_frame, text="＋ 追加", command=self.add_drone_entry).pack(
            side="left", expand=True, fill="x", padx=(0, 2)
        )
        ttk.Button(
            ip_button_frame, text="－ 削除", command=self.remove_drone_entry
        ).pack(side="left", expand=True, fill="x", padx=(2, 0))

        ttk.Button(ip_frame, text="⚙️ 設定を保存", command=self.save_config).pack(
            fill="x", pady=(10, 5)
        )

        self.connect_btn = ttk.Button(
            ip_frame,
            text="📡 ドローンに接続",
            command=self.auto_detect_and_connect,
        )
        self.connect_btn.pack(fill="x", pady=(5, 0))

    def _create_project_selection_section(self, parent):
        """② プロジェクト選択 & 解析セクションを作成"""
        file_frame = ttk.LabelFrame(
            parent, text="② プロジェクト選択 & 解析", padding="10"
        )
        file_frame.pack(fill="x", pady=(0, 15))

        self.sb3_path_label = ttk.Label(file_frame, text="ファイルが選択されていません")
        self.sb3_path_label.pack(fill="x", pady=(0, 10))
        self.sb3_path_label.bind(
            "<Configure>", lambda e: self.sb3_path_label.config(wraplength=e.width - 10)
        )

        ttk.Button(
            file_frame, text="📂 Scratchファイルを開く", command=self.select_file
        ).pack(fill="x", pady=(0, 5))

        self.parse_btn = ttk.Button(
            file_frame,
            text="🔄 タイムラインを解析",
            command=self.parse_scratch_project,
            state="disabled",
        )
        self.parse_btn.pack(fill="x", pady=(0, 5))

        # タイムラインビューアーボタン
        self.timeline_viewer_btn = ttk.Button(
            file_frame,
            text="📊 タイムラインを表示",
            command=self.open_timeline_viewer,
            state="disabled",
        )
        self.timeline_viewer_btn.pack(fill="x", pady=(0, 10))

        # プロジェクト管理ボタン
        project_btn_frame = ttk.Frame(file_frame)
        project_btn_frame.pack(fill="x")

        ttk.Button(
            project_btn_frame,
            text="💾 プロジェクト保存",
            command=self.save_project,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))

        ttk.Button(
            project_btn_frame,
            text="📁 プロジェクト読込",
            command=self.load_project,
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

    def _create_audio_selection_section(self, parent):
        """④ 音源ファイル選択セクションを作成"""
        audio_frame = ttk.LabelFrame(
            parent, text="④ 音源ファイル (オプション)", padding="10"
        )
        audio_frame.pack(fill="x", pady=(0, 15))

        self.audio_path_label = ttk.Label(
            audio_frame, text="音楽ファイルが選択されていません"
        )
        self.audio_path_label.pack(fill="x", pady=(0, 10))
        self.audio_path_label.bind(
            "<Configure>",
            lambda e: self.audio_path_label.config(wraplength=e.width - 10),
        )

        # メドレー管理ボタン
        ttk.Button(
            audio_frame, text="🎼 メドレー管理", command=self.open_music_manager
        ).pack(fill="x", pady=(0, 5))

        # クイック選択ボタン
        ttk.Button(
            audio_frame, text="🎶 クイック選択", command=self.select_audio_file
        ).pack(fill="x")

    def _create_show_control_section(self, parent):
        """③ ショー実行セクションを作成"""
        action_frame = ttk.LabelFrame(parent, text="③ ショー実行", padding="10")
        action_frame.pack(fill="x", pady=(0, 15))

        self.connect_btn = ttk.Button(
            action_frame,
            text="📡 ドローンに接続",
            command=self.connect_drones,
            state="disabled",
        )
        self.connect_btn.pack(fill="x", pady=(0, 5))

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

    def _create_status_bar(self, parent):
        """ステータスバーを作成"""
        status_bar = ttk.Frame(parent, padding=(5, 5))
        status_bar.grid(row=0, column=1, sticky="ew", pady=(0, 5))

        ttk.Label(status_bar, text="ステータス:", style="Header.TLabel").pack(
            side="left"
        )
        ttk.Label(status_bar, textvariable=self.show_status).pack(side="left", padx=5)

    def _create_log_panels(self, parent):
        """タイムラインと通信ログパネルを作成"""
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        log_pane = ttk.PanedWindow(right_frame, orient="horizontal")
        log_pane.pack(fill="both", expand=True)

        # タイムラインパネル
        timeline_frame = ttk.Frame(log_pane)
        log_pane.add(timeline_frame, weight=1)

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

        # 通信ログパネル
        log_frame = ttk.Frame(log_pane)
        log_pane.add(log_frame, weight=1)

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
        self._configure_text_tags()

    def _configure_text_tags(self):
        """テキストウィジェットのタグを設定"""
        # ログテキストのタグ
        self.log_text.tag_config(LOG_LEVEL_INFO, foreground="black")
        self.log_text.tag_config(LOG_LEVEL_SUCCESS, foreground=COLOR_SUCCESS)
        self.log_text.tag_config(LOG_LEVEL_WARNING, foreground=COLOR_WARNING)
        self.log_text.tag_config(LOG_LEVEL_ERROR, foreground=COLOR_ERROR)

        # スケジュールテキストのタグ
        self.schedule_text.tag_config(
            EVENT_TYPE_TAKEOFF,
            foreground=COLOR_SUCCESS,
            font=(self.font_monospace[0], self.font_monospace[1], "bold"),
        )
        self.schedule_text.tag_config(EVENT_TYPE_INFO, foreground="black")
        self.schedule_text.tag_config(EVENT_TYPE_WAIT, foreground="blue")
        self.schedule_text.tag_config(EVENT_TYPE_WARNING, foreground=COLOR_ERROR)
        self.schedule_text.tag_config(
            "HEADER", foreground=COLOR_PRIMARY, font=self.font_header
        )
        self.schedule_text.tag_config("HIGHLIGHT", background=COLOR_HIGHLIGHT)
        self.schedule_text.tag_config(
            EVENT_TYPE_LAND,
            foreground=COLOR_DANGER,
            font=(self.font_monospace[0], self.font_monospace[1], "bold"),
        )

    def add_drone_entry(self, name=None, ip=""):
        """
        ドローンエントリーを追加

        Args:
            name: ドローン名（デフォルト: Tello_A, Tello_B, ...）
            ip: IPアドレス
        """
        drone_count = len(self.drone_entry_widgets)
        if name is None:
            name = f"{DEFAULT_DRONE_PREFIX}{chr(65 + drone_count)}"

        widget_dict = {}
        row_frame = ttk.Frame(self.ip_entry_frame)
        row_frame.pack(fill="x", pady=2)

        label = ttk.Label(row_frame, text=f"{name}:")
        label.pack(side="left", padx=(0, 5))

        entry = ttk.Entry(row_frame)
        entry.pack(side="left", expand=True, fill="x")
        entry.insert(0, ip)

        widget_dict.update({"name": name, "frame": row_frame, "ip_widget": entry})
        self.drone_entry_widgets.append(widget_dict)

    def remove_drone_entry(self):
        """最後のドローンエントリーを削除"""
        if not self.drone_entry_widgets:
            return
        widgets_to_remove = self.drone_entry_widgets.pop()
        widgets_to_remove["frame"].destroy()

    def load_config(self):
        """設定ファイルからドローン設定を読み込む"""
        try:
            with open(CONFIG_FILENAME, "r") as f:
                config_data = json.load(f)

            # 既存のエントリーをクリア
            while self.drone_entry_widgets:
                self.remove_drone_entry()

            # 設定からエントリーを追加
            for name, ip in config_data.items():
                self.add_drone_entry(name=name, ip=ip)

            self.log(
                {
                    "level": LOG_LEVEL_INFO,
                    "message": f"{CONFIG_FILENAME} から設定を読み込みました。",
                }
            )
        except FileNotFoundError:
            self.log(
                {
                    "level": LOG_LEVEL_WARNING,
                    "message": "設定ファイルが見つかりません。ドローンを１台以上IPアドレスを入力し、保存してください。",
                }
            )
            if not self.drone_entry_widgets:
                self.add_drone_entry()
        except Exception as e:
            self.log(
                {"level": LOG_LEVEL_ERROR, "message": f"設定の読み込みエラー: {e}"}
            )

    def save_config(self):
        """ドローン設定を設定ファイルに保存"""
        config_data = {
            widgets["name"]: widgets["ip_widget"].get()
            for widgets in self.drone_entry_widgets
        }
        try:
            with open(CONFIG_FILENAME, "w") as f:
                json.dump(config_data, f, indent=4)

            self.log(
                {
                    "level": LOG_LEVEL_INFO,
                    "message": f"{CONFIG_FILENAME} に設定を保存しました。",
                }
            )
            messagebox.showinfo("成功", "IPアドレスを保存しました。")
        except Exception as e:
            messagebox.showerror("エラー", f"設定の保存に失敗しました: {e}")

    def auto_detect_and_connect(self):
        """Wi-Fiドングルに接続されたTelloドローンを自動検出して接続"""
        self.log(
            {
                "level": LOG_LEVEL_INFO,
                "message": "Telloドローンの自動検出と接続を開始しています...",
            }
        )

        # スレッドで実行（UIがブロックされないように）
        thread = threading.Thread(target=self._auto_detect_and_connect_thread)
        thread.daemon = True
        thread.start()

    def _auto_detect_and_connect_thread(self):
        """自動検出と接続処理を実行するスレッド"""
        try:
            network_manager = NetworkManager()

            # 接続されているTelloを取得
            connected_tellos = network_manager.get_connected_tellos()

            if not connected_tellos:
                self.log(
                    {
                        "level": LOG_LEVEL_WARNING,
                        "message": "接続されているTelloドローンが見つかりません。周囲をスキャンして接続を試みています...",
                    }
                )

                # 周囲のTelloネットワークをスキャンして接続を試みる
                self.log(
                    {
                        "level": LOG_LEVEL_INFO,
                        "message": "周囲のTelloネットワークをスキャン中...",
                    }
                )
                network_manager.connect_all_tellos(log_callback=self._log_callback)

                # 再度接続状態を確認
                import time

                time.sleep(5)  # 接続確立を待つ
                connected_tellos = network_manager.get_connected_tellos()

            if not connected_tellos:
                self.log(
                    {
                        "level": LOG_LEVEL_ERROR,
                        "message": "Telloドローンへの接続に失敗しました。Telloの電源と距離を確認してください。",
                    }
                )
                return

            # 既存のエントリーをクリア
            while self.drone_entry_widgets:
                self.remove_drone_entry()

            # 検出したIPアドレスをTello_A, Tello_Bなどの順に追加
            for idx, tello_info in enumerate(connected_tellos):
                drone_name = f"Tello_{chr(65 + idx)}"  # A, B, C, ...
                ip = tello_info["ip"]
                self.add_drone_entry(name=drone_name, ip=ip)

                self.log(
                    {
                        "level": LOG_LEVEL_INFO,
                        "message": f"検出: {drone_name} -> {ip} ({tello_info['ssid']})",
                    }
                )

            self.log(
                {
                    "level": LOG_LEVEL_SUCCESS,
                    "message": f"{len(connected_tellos)}台のTelloドローンを検出しました。",
                }
            )

            # 自動的に設定を保存
            self.save_config()

            # ドローンへの接続処理を実行
            self.connect_drones()

        except Exception as e:
            self.log(
                {
                    "level": LOG_LEVEL_ERROR,
                    "message": f"接続エラー: {e}",
                }
            )

    def _log_callback(self, message):
        """NetworkManagerからのログコールバック"""
        self.log(
            {
                "level": LOG_LEVEL_INFO,
                "message": message,
            }
        )

    def select_file(self):
        """Scratchプロジェクトファイルを選択"""
        path = filedialog.askopenfilename(
            title="Scratch 3 プロジェクトファイルを選択",
            filetypes=SUPPORTED_PROJECT_FILES,
        )

        if path:
            self.sb3_path.set(path)
            self.sb3_path_label.configure(text=path.split("/")[-1])
            self._reset_ui_to_file_selected_state()
            self.log(
                {"level": LOG_LEVEL_INFO, "message": f"選択されたファイル: {path}"}
            )

    def select_audio_file(self):
        """音楽ファイルをクイック選択（単一ファイル）"""
        path = filedialog.askopenfilename(
            title="音楽ファイルを選択", filetypes=SUPPORTED_AUDIO_FILES
        )

        if path:
            self.audio_path.set(path)
            self.music_list = []  # メドレーリストをクリア
            self.is_medley_mode = False
            filename = path.split("/")[-1].split("\\")[-1]
            self.audio_path_label.configure(text=f"単一ファイル: {filename}")
            self.log(
                {
                    "level": LOG_LEVEL_INFO,
                    "message": f"選択された音楽ファイル: {filename}",
                }
            )

    def download_from_youtube(self):
        """YouTube URLから音源を取得"""
        if not self.youtube_downloader.is_available():
            messagebox.showerror(
                "エラー",
                "yt-dlpがインストールされていません。\n\n"
                "以下のコマンドでインストールしてください:\n"
                "pip install yt-dlp",
            )
            return

        # URL入力ダイアログを作成
        dialog = tk.Toplevel(self.master)
        dialog.title("YouTube音源設定")
        dialog.geometry("500x200")
        dialog.transient(self.master)
        dialog.grab_set()

        # 中央に配置
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        # コンテンツフレーム
        content_frame = ttk.Frame(dialog, padding="20")
        content_frame.pack(fill="both", expand=True)

        ttk.Label(
            content_frame,
            text="YouTube動画のURLを入力してください:",
            font=self.font_normal,
        ).pack(anchor="w", pady=(0, 5))

        ttk.Label(
            content_frame,
            text="※再生時に音声データを一時ファイルとしてキャッシュします",
            font=("Arial", 8),
            foreground="gray",
        ).pack(anchor="w", pady=(0, 10))

        url_entry = ttk.Entry(content_frame, font=self.font_normal)
        url_entry.pack(fill="x", pady=(0, 10))
        url_entry.focus()

        # ステータスラベル
        status_label = ttk.Label(content_frame, text="", foreground="gray")
        status_label.pack(fill="x", pady=(0, 10))

        # ボタンフレーム
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill="x")

        result = {"youtube_url": None}

        def on_add():
            url = url_entry.get().strip()
            if not url:
                messagebox.showwarning("警告", "URLを入力してください。", parent=dialog)
                return

            if not self.youtube_downloader.is_youtube_url(url):
                messagebox.showerror(
                    "エラー", "有効なYouTube URLではありません。", parent=dialog
                )
                return

            # URL検証中の表示
            status_label.config(text="YouTube動画情報を確認中...")
            dialog.update()

            # 動画情報を取得
            video_info = self.youtube_downloader.get_video_info(url)

            if video_info:
                result["youtube_url"] = url
                result["title"] = video_info.get("title", "Unknown")
                messagebox.showinfo(
                    "成功",
                    f"YouTube動画を追加しました。\n\nタイトル: {result['title']}",
                    parent=dialog,
                )
                dialog.destroy()
            else:
                status_label.config(text="")
                messagebox.showerror(
                    "エラー",
                    "動画情報の取得に失敗しました。\nURLを確認してください。",
                    parent=dialog,
                )

        def on_cancel():
            dialog.destroy()

        ttk.Button(
            button_frame, text="追加", command=on_add, style="Accent.TButton"
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ttk.Button(button_frame, text="キャンセル", command=on_cancel).pack(
            side="left", fill="x", expand=True
        )

        # Enterキーで追加
        url_entry.bind("<Return>", lambda e: on_add())

        dialog.wait_window()

        # URLが追加された場合、音楽を設定
        if result["youtube_url"]:
            youtube_url = result["youtube_url"]
            title = result.get("title", "YouTube動画")

            # メドレーリストをクリアして単一URLに設定
            self.music_player.set_music_list([])
            self.music_player.set_music(youtube_url)
            self.audio_path.set(youtube_url)

            # UI更新
            self.audio_path_label.configure(
                text=f"YouTube: {title[:40]}...", foreground=COLOR_SUCCESS
            )
            self.log({"level": "INFO", "message": f"YouTube音源を設定: {title}"})

    def open_music_manager(self):
        """音楽管理ウィンドウを開く"""
        from gui.music_manager_window import MusicManagerWindow

        MusicManagerWindow(
            self.master,
            self.music_player,
            self.music_list,
            self._on_music_list_saved,
            youtube_titles=self.youtube_titles,
            bpm_data=self.bpm_data,
        )

    def _on_music_list_saved(
        self,
        music_list: list,
        interval: float,
        youtube_titles: dict = None,
        bpm_data: dict = None,
    ):
        """
        音楽管理ウィンドウから音楽リストが保存された時の処理

        Args:
            music_list: 保存された音楽ファイルリスト
            interval: 曲間インターバル（秒）
            youtube_titles: YouTubeタイトルの辞書
            bpm_data: BPM情報の辞書
        """
        self.music_list = music_list

        # YouTubeタイトルを更新
        if youtube_titles:
            self.youtube_titles.update(youtube_titles)

        # BPMデータを更新
        if bpm_data:
            self.bpm_data.update(bpm_data)

        if music_list:
            self.is_medley_mode = True
            self.audio_path.set("")  # 単一ファイルパスをクリア
            interval_text = f" (間隔: {interval}秒)" if interval > 0 else ""
            self.audio_path_label.configure(
                text=f"メドレー: {len(music_list)}曲{interval_text}"
            )
            self.log(
                {
                    "level": LOG_LEVEL_INFO,
                    "message": f"メドレーを設定しました（{len(music_list)}曲、インターバル: {interval}秒）",
                }
            )
        else:
            self.is_medley_mode = False
            self.audio_path.set("")
            self.audio_path_label.configure(text="音楽ファイルが選択されていません")
            self.log({"level": LOG_LEVEL_INFO, "message": "音楽設定をクリアしました"})

    def open_timeline_viewer(self):
        """タイムラインビューアーウィンドウを開く"""
        if not self.schedule:
            messagebox.showwarning(
                "警告",
                "タイムラインが生成されていません。\n先にScratchファイルを解析してください。",
            )
            return

        from gui.timeline_viewer_window import TimelineViewerWindow

        TimelineViewerWindow(
            self.master,
            self.schedule,
            self.total_time,
            self.music_list,
            self.music_player,
        )

    def save_project(self):
        """プロジェクトを保存"""
        # スケジュールが解析されていない場合
        if not self.schedule:
            messagebox.showwarning(
                "警告",
                "プロジェクトを保存するには、まずタイムラインを解析してください。",
            )
            return

        # ファイル名のデフォルトを設定
        default_name = "project"
        if self.sb3_path.get():
            import os

            sb3_name = os.path.basename(self.sb3_path.get())
            default_name = os.path.splitext(sb3_name)[0]

        # 保存先を選択
        save_path = filedialog.asksaveasfilename(
            title="プロジェクトを保存",
            defaultextension=self.project_manager.PROJECT_EXTENSION,
            initialfile=default_name,
            filetypes=[
                (
                    "Telloプロジェクト",
                    f"*{self.project_manager.PROJECT_EXTENSION}",
                ),
                ("すべてのファイル", "*.*"),
            ],
        )

        if not save_path:
            return

        # ドローン設定を取得
        drone_config = {
            widgets["name"]: widgets["ip_widget"].get()
            for widgets in self.drone_entry_widgets
        }

        # 音楽リストを取得
        music_list = self.music_player.get_music_list()
        if not music_list and self.audio_path.get():
            # 単一ファイルの場合
            music_list = [self.audio_path.get()]

        # プロジェクトを保存
        success = self.project_manager.save_project(
            project_path=save_path,
            sb3_path=self.sb3_path.get(),
            schedule=self.schedule,
            total_time=self.total_time,
            time_to_line_map=self.time_to_line_map,
            music_list=music_list,
            music_interval=self.music_player.get_interval(),
            drone_config=drone_config,
            youtube_titles=self.youtube_titles,
            bpm_data=self.bpm_data,
        )

        if success:
            self.current_project_path = save_path
            messagebox.showinfo("成功", f"プロジェクトを保存しました。\n{save_path}")
        else:
            messagebox.showerror("エラー", "プロジェクトの保存に失敗しました。")

    def load_project(self):
        """プロジェクトを読み込み"""
        # ファイルを選択
        load_path = filedialog.askopenfilename(
            title="プロジェクトを読み込み",
            filetypes=[
                (
                    "Telloプロジェクト",
                    f"*{self.project_manager.PROJECT_EXTENSION}",
                ),
                ("すべてのファイル", "*.*"),
            ],
        )

        if not load_path:
            return

        # プロジェクトを読み込み
        project_data = self.project_manager.load_project(load_path)

        if not project_data:
            messagebox.showerror("エラー", "プロジェクトの読み込みに失敗しました。")
            return

        # データを復元
        self.current_project_path = load_path

        # .sb3ファイルを設定
        if project_data["sb3_path"]:
            self.sb3_path.set(project_data["sb3_path"])
            import os

            filename = os.path.basename(project_data["sb3_path"])
            self.sb3_path_label.configure(text=filename)
            self.parse_btn["state"] = "normal"

        # スケジュールとタイムライン情報を復元
        self.schedule = project_data["schedule"]
        self.total_time = project_data["total_time"]
        self.time_to_line_map = project_data["time_to_line_map"]

        # タイムラインを表示
        if self.schedule:
            self._restore_timeline_display()

        # 音楽設定を復元
        music_paths = project_data["music_paths"]
        music_interval = project_data["music_interval"]

        # YouTubeタイトルを復元
        self.youtube_titles = project_data.get("youtube_titles", {})

        # BPMデータを復元
        self.bpm_data = project_data.get("bpm_data", {})

        if music_paths:
            # 音楽リストを内部変数に保存
            self.music_list = music_paths

            # 音楽プレイヤーに設定
            self.music_player.set_music_list(music_paths)
            self.music_player.set_interval(music_interval)

            # メドレーモードに設定
            self.is_medley_mode = len(music_paths) > 1

            interval_text = f" (間隔: {music_interval}秒)" if music_interval > 0 else ""
            self.audio_path_label.configure(
                text=f"メドレー: {len(music_paths)}曲{interval_text}",
                foreground=COLOR_SUCCESS,
            )

            # ログ出力
            self.log(
                {
                    "level": "INFO",
                    "message": f"音楽を復元しました: {len(music_paths)}曲 (間隔: {music_interval}秒)",
                }
            )
        else:
            self.music_list = []
            self.is_medley_mode = False
            self.audio_path_label.configure(
                text="設定されていません", foreground="#666"
            )

        # ドローン設定を復元
        drone_config = project_data["drone_config"]
        if drone_config:
            # 既存のエントリをクリア
            while self.drone_entry_widgets:
                self.remove_drone_entry()

            # 設定からエントリを追加
            for name, ip in drone_config.items():
                self.add_drone_entry(name=name, ip=ip)

        messagebox.showinfo("成功", f"プロジェクトを読み込みました。\n{load_path}")

        self.log(
            {"level": "INFO", "message": f"プロジェクトを読み込みました: {load_path}"}
        )

    def _restore_timeline_display(self):
        """保存されたタイムラインを表示エリアに復元"""
        self.schedule_text.config(state="normal")
        self.schedule_text.delete(1.0, tk.END)

        if not self.schedule:
            self.schedule_text.config(state="disabled")
            return

        # イベントを時間ごとにグループ化
        grouped_events = {}
        for event in self.schedule:
            if event["time"] not in grouped_events:
                grouped_events[event["time"]] = []
            grouped_events[event["time"]].append(event)

        # タイムラインを構築
        current_line = 1
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

        self.schedule_text.config(state="disabled")

        # ボタンの状態を更新
        self.timeline_viewer_btn["state"] = "normal"
        self.connect_btn["state"] = "normal"
        self.show_status.set("タイムライン読み込み完了")

    def parse_scratch_project(self):
        """Scratchプロジェクトを解析してタイムラインを生成"""
        path = self.sb3_path.get()
        if not path:
            return

        # ログをクリア
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

        self.log(
            {"level": LOG_LEVEL_INFO, "message": "Scratchファイルの解析を開始します..."}
        )

        # 解析実行
        parser = ScratchProjectParser(path, self.log_queue)
        self.schedule, self.total_time = parser.parse_to_schedule()

        # タイムラインを表示
        self._display_timeline()

    def _display_timeline(self):
        """解析結果をタイムラインに表示"""
        self.schedule_text.config(state="normal")
        self.schedule_text.delete(1.0, tk.END)
        self.time_to_line_map = {}

        if self.schedule:
            # ヘッダー
            self.schedule_text.insert(
                tk.END,
                f"--- 生成されたタイムライン (予想総時間: {self.total_time:.2f}秒) ---\n\n",
                "HEADER",
            )

            current_line = 3

            # 時間ごとにイベントをグループ化
            grouped_events = {
                t: [e for e in self.schedule if e["time"] == t]
                for t in sorted(list(set(e["time"] for e in self.schedule)))
            }

            # イベントを表示
            for time, events in grouped_events.items():
                start_line = current_line

                for event in events:
                    log_msg = self._format_event_message(time, event)
                    evt_type = event.get("type", EVENT_TYPE_INFO)
                    self.schedule_text.insert(tk.END, log_msg, evt_type)
                    current_line += 1

                self.time_to_line_map[time] = {
                    "start": start_line,
                    "end": current_line - 1,
                }

            self.log(
                {
                    "level": LOG_LEVEL_SUCCESS,
                    "message": "解析に成功しました。ドローンに接続してください。",
                }
            )
            self.connect_btn["state"] = "normal"
            self.timeline_viewer_btn["state"] = (
                "normal"  # タイムラインビューアーボタンを有効化
            )
            self.show_status.set("解析完了。ドローンに接続してください。")
        else:
            self.schedule_text.insert(
                tk.END,
                "ファイルから有効なスケジュールを生成できませんでした。\n",
                LOG_LEVEL_ERROR,
            )
            self.schedule_text.insert(
                tk.END,
                "ヒント: スプライトに「緑の旗が押されたとき」ブロックがありますか？\n",
                LOG_LEVEL_INFO,
            )
            self.show_status.set("解析失敗")

        self.schedule_text.config(state="disabled")

    def _format_event_message(self, time, event):
        """
        イベントメッセージをフォーマット

        Args:
            time: イベント時刻
            event: イベント辞書

        Returns:
            フォーマットされたメッセージ文字列
        """
        evt_type = event.get("type")
        target = event.get("target", "N/A")

        if evt_type == EVENT_TYPE_TAKEOFF:
            return f"{time: >6.2f}s | {target: <8} | {event.get('text', '')}\n"
        elif evt_type == EVENT_TYPE_COMMAND:
            return f"{time: >6.2f}s | {target: <8} | 実行: {event.get('command', '')}\n"
        elif evt_type == EVENT_TYPE_WAIT:
            return f"{time: >6.2f}s | {target: <8} | 待機: {event.get('text', '')}\n"
        elif evt_type == EVENT_TYPE_WARNING:
            return f"{time: >6.2f}s | {event.get('text', '')}\n"
        elif evt_type == EVENT_TYPE_LAND:
            return f"{time: >6.2f}s | {target: <8} | {event.get('text', '')}\n"
        else:
            return f"{time: >6.2f}s | {event.get('text', '')}\n"

    def connect_drones(self):
        """ドローンに接続"""
        self.connect_btn["state"] = "disabled"
        self.show_status.set("ドローンに接続中...")

        drones_config = [
            {"name": w["name"], "pc_ip": w["ip_widget"].get()}
            for w in self.drone_entry_widgets
        ]

        if not all(c["pc_ip"] for c in drones_config):
            messagebox.showerror(
                "エラー", "開始前に、すべてのIPアドレスを入力してください。"
            )
            self.connect_btn["state"] = "normal"
            return

        show_runner = ShowRunner(
            drones_config,
            self.schedule,
            self.stop_event,
            self.log_queue,
            self.total_time,
        )
        threading.Thread(target=show_runner.connect, daemon=True).start()

    def start_show(self):
        """ショーを開始"""
        self._set_ui_for_show_running(True)
        self.stop_event.clear()
        self.show_status.set("ショー実行中...")

        # 音楽再生（3秒遅延）
        if self.is_medley_mode and self.music_list:
            # メドレーモード
            self.music_player.set_music_list(self.music_list)
            self.music_player.play_medley(delay_seconds=3.0)
        elif self.audio_path.get():
            # 単一ファイルモード
            self.music_player.play(self.audio_path.get(), delay_seconds=3.0)

        show_runner = ShowRunner(
            None,
            self.schedule,
            self.stop_event,
            self.log_queue,
            self.total_time,
            self.controllers,
            self.audio_path.get(),
        )

        self.show_thread = threading.Thread(target=show_runner.run_show, daemon=True)
        self.show_thread.start()

    def emergency_stop(self):
        """緊急停止"""
        self.log(
            {
                "level": LOG_LEVEL_ERROR,
                "message": "\n!!! ユーザーによる緊急停止が要求されました !!!",
            }
        )

        # 音楽を停止
        self.music_player.stop()

        self.stop_event.set()
        self.show_status.set("緊急停止 - 着陸中...")
        self.stop_btn["state"] = "disabled"

    def _reset_ui_to_parsed_state(self):
        """UIを解析完了状態にリセット"""
        self.controllers = {}
        self.stop_event.clear()
        self.stop_btn["state"] = "disabled"
        self.start_btn["state"] = "disabled"
        self.connect_btn["state"] = "normal"
        self.parse_btn["state"] = "normal"
        self.connect_btn.config(text="📡 ドローンに接続")
        self.show_status.set("準備完了。ドローンに接続してください。")
        self.update_timeline_highlight(None)

    def _set_ui_for_show_running(self, is_running):
        """
        ショー実行中のUI状態を設定

        Args:
            is_running: ショーが実行中かどうか
        """
        state = "disabled" if is_running else "normal"
        self.start_btn["state"] = state
        self.parse_btn["state"] = state
        self.connect_btn["state"] = state
        self.stop_btn["state"] = "normal" if is_running else "disabled"

    def _reset_ui_to_file_selected_state(self):
        """UIをファイル選択状態にリセット"""
        self.parse_btn["state"] = "normal"
        self.connect_btn["state"] = "disabled"
        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "disabled"
        self.timeline_viewer_btn["state"] = "disabled"
        self.connect_btn.config(text="📡 ドローンに接続")
        self.show_status.set("ファイル選択済み。解析してください。")

    def log(self, log_item):
        """
        ログメッセージをキューに追加

        Args:
            log_item: ログアイテム（辞書またはメッセージ文字列）
        """
        self.log_queue.put(log_item)

    def process_log_queue(self):
        """ログキューを処理してUIを更新（バッチ処理で最適化）"""
        try:
            messages_to_add = []
            max_batch_size = 50  # 1回の処理で最大50件まで
            processed = 0

            while not self.log_queue.empty() and processed < max_batch_size:
                log_item = self.log_queue.get_nowait()
                processed += 1

                # 特殊なメッセージタイプの処理
                if isinstance(log_item, dict) and "type" in log_item:
                    msg_type = log_item["type"]

                    if msg_type == "highlight":
                        self.update_timeline_highlight(log_item.get("time"))
                        continue
                    elif msg_type == "clear_highlight":
                        self.update_timeline_highlight(None)
                        continue
                    elif msg_type == "connection_success":
                        self.controllers = log_item["controllers"]
                        self.start_btn["state"] = "normal"
                        self.connect_btn.config(text="✓ 接続済み")
                        self.show_status.set("接続完了。ショーを開始できます。")
                        continue
                    elif msg_type == "connection_fail":
                        self.connect_btn["state"] = "normal"
                        self.show_status.set("接続に失敗しました。再試行してください。")
                        continue
                    elif msg_type == "show_finished":
                        # 音楽を停止
                        self.music_player.stop()
                        self._reset_ui_to_parsed_state()
                        continue

                # 通常のログメッセージをバッチに追加
                if isinstance(log_item, dict):
                    level = log_item.get("level", LOG_LEVEL_INFO)
                    message = log_item.get("message", "")
                else:
                    level = LOG_LEVEL_INFO
                    message = str(log_item)

                messages_to_add.append((message, level))

            # バッチでログを追加（UI操作を最小化）
            if messages_to_add:
                self.log_text.config(state="normal")
                for message, level in messages_to_add:
                    self.log_text.insert(tk.END, message + "\n", level)
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")
        finally:
            self.master.after(LOG_QUEUE_UPDATE_INTERVAL, self.process_log_queue)

    def update_timeline_highlight(self, current_time):
        """
        タイムラインのハイライトを更新

        Args:
            current_time: 現在の時刻（Noneの場合はハイライトをクリア）
        """
        self.schedule_text.config(state="normal")

        # 前のハイライトを削除
        if self.last_highlighted_lines:
            self.schedule_text.tag_remove(
                "HIGHLIGHT",
                f"{self.last_highlighted_lines['start']}.0",
                f"{self.last_highlighted_lines['end']}.end",
            )
            self.last_highlighted_lines = None

        # 新しいハイライトを追加
        if current_time is not None and current_time in self.time_to_line_map:
            line_info = self.time_to_line_map[current_time]
            self.schedule_text.tag_add(
                "HIGHLIGHT", f"{line_info['start']}.0", f"{line_info['end']}.end"
            )
            self.schedule_text.see(f"{line_info['start']}.0")
            self.last_highlighted_lines = line_info

        self.schedule_text.config(state="disabled")

    def on_closing(self):
        """ウィンドウを閉じる際の処理"""
        if self.show_thread and self.show_thread.is_alive():
            if messagebox.askyesno(
                "終了確認", "ショーが実行中です。停止して終了しますか？"
            ):
                self.emergency_stop()
                # 一時ファイルをクリーンアップ
                if self.current_project_path:
                    self.project_manager.cleanup_temp_files(self.current_project_path)
                self.master.destroy()
        else:
            # 音楽プレイヤーを停止
            self.music_player.stop()
            # 一時ファイルをクリーンアップ
            if self.current_project_path:
                self.project_manager.cleanup_temp_files(self.current_project_path)
            self.master.destroy()
