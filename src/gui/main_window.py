"""
メインウィンドウモジュール (安全版UI)
"""
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from queue import Queue
import os

# パス設定の修正（インポートエラー対策）
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import *

# coreパッケージからのインポート
try:
    from core.scratch_parser import ScratchProjectParser
    from core.show_runner import ShowRunner
    from core.network_manager import NetworkManager
    from core.music_player import MusicPlayer
except ImportError as e:
    # 開発環境用フォールバック
    print(f"Import Error: {e}. Trying fallback...")
    try:
        from scratch_parser import ScratchProjectParser
        from show_runner import ShowRunner
        from music_player import MusicPlayer
        from network_manager import NetworkManager
    except ImportError:
        NetworkManager = None

from .music_manager_window import MusicManagerWindow
from .timeline_viewer_window import TimelineViewerWindow

# --- 定数定義 ---
FONT_NORMAL = ("Yu Gothic UI", 10)
FONT_BOLD_LARGE = ("Yu Gothic UI", 11, "bold")
FONT_HEADER = ("Yu Gothic UI", 12, "bold")
FONT_MONOSPACE = ("Consolas", 9)
COLOR_PRIMARY = "#007acc"
COLOR_PRIMARY_HOVER = "#005f9e"
COLOR_PRIMARY_DISABLED = "#cccccc"
COLOR_DANGER = "#e51400"
COLOR_DANGER_HOVER = "#b00f00"
COLOR_DANGER_DISABLED = "#ffcccc"
COLOR_SUCCESS = "#107c10"
COLOR_WARNING = "#d83b01"
COLOR_ERROR = "red"
COLOR_BACKGROUND = "#f0f0f0"
COLOR_TEXT = "#000000"
COLOR_HIGHLIGHT = "#ffff99"
MAIN_PADDING = 10

class TelloApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Tello Scratch Controller (安全版)")
        self.master.geometry("1100x850")
        self.master.minsize(800, 600)
        self.setup_styles()

        self.drone_entry_widgets = []
        self.schedule = None
        self.total_time = 0.0
        self.time_to_line_map = {}
        self.sb3_path = tk.StringVar()
        self.audio_path = tk.StringVar()
        self.show_status = tk.StringVar(value="準備完了")
        self.log_queue = Queue()
        self.stop_event = threading.Event()
        self.controllers = {}
        self.show_thread = None
        self.music_list = []
        self.music_player = MusicPlayer(self.log_queue)

        self._create_widgets()
        self.load_config()
        self.process_log_queue()
        self._update_telemetry_loop()

    def setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=COLOR_BACKGROUND, foreground="black", font=FONT_NORMAL)
        s.configure("TFrame", background=COLOR_BACKGROUND)
        s.configure("TLabel", background=COLOR_BACKGROUND, foreground="black")
        s.configure("Header.TLabel", font=FONT_HEADER, foreground=COLOR_PRIMARY)
        s.configure("TLabelframe", background=COLOR_BACKGROUND)
        s.configure("TLabelframe.Label", font=FONT_BOLD_LARGE, foreground=COLOR_TEXT)
        s.configure("TButton", font=FONT_NORMAL, padding=6)
        s.configure("Accent.TButton", font=FONT_NORMAL, padding=8, foreground="white", background=COLOR_PRIMARY)
        s.map("Accent.TButton", background=[("active", COLOR_PRIMARY_HOVER), ("disabled", COLOR_PRIMARY_DISABLED)])
        s.configure("Stop.TButton", font=FONT_NORMAL, padding=8, foreground="white", background=COLOR_DANGER)
        s.map("Stop.TButton", background=[("active", COLOR_DANGER_HOVER), ("disabled", COLOR_DANGER_DISABLED)])
        s.configure("Setup.TButton", font=FONT_NORMAL, padding=6, foreground="white", background="#28a745")
        s.map("Setup.TButton", background=[("active", "#218838")])

    def _create_widgets(self):
        main_frame = ttk.Frame(self.master, padding=MAIN_PADDING)
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=0, minsize=350)
        main_frame.grid_columnconfigure(1, weight=1)

        left_canvas = tk.Canvas(main_frame, bg=COLOR_BACKGROUND, highlightthickness=0)
        left_canvas.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
        left_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=left_canvas.yview)
        left_scrollbar.grid(row=0, column=0, rowspan=2, sticky="nse", padx=(0, 10))
        left_frame = ttk.Frame(left_canvas)
        left_canvas_frame = left_canvas.create_window((0, 0), window=left_frame, anchor="nw")

        def configure_scroll_region(event): left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        def configure_canvas_width(event): left_canvas.itemconfig(left_canvas_frame, width=event.width)
        left_frame.bind("<Configure>", configure_scroll_region)
        left_canvas.bind("<Configure>", configure_canvas_width)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        
        def on_mousewheel(event): left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        left_canvas.bind_all("<MouseWheel>", on_mousewheel)

        self._create_drone_config_section(left_frame)
        self._create_project_selection_section(left_frame)
        self._create_audio_selection_section(left_frame)
        self._create_show_control_section(left_frame)

        self._create_status_bar(main_frame)
        self._create_log_panels(main_frame)

    def _create_drone_config_section(self, parent):
        ip_frame = ttk.LabelFrame(parent, text="① ドローン設定 & IP自動固定", padding="10")
        ip_frame.pack(fill="x", pady=(0, 15))

        setup_btn = ttk.Button(ip_frame, text="⚡ 全自動セットアップ (安全版)", command=self.full_auto_setup, style="Setup.TButton")
        setup_btn.pack(fill="x", pady=(0, 10))
        
        ttk.Label(ip_frame, text="※家のWi-Fiなど、すでに接続中のアダプタは無視します。\n※ドングルは「未接続」の状態にして押してください。", font=("", 9), foreground="gray").pack(pady=(0,5))

        self.ip_entry_frame = ttk.Frame(ip_frame)
        self.ip_entry_frame.pack(fill="x")

        btn_f = ttk.Frame(ip_frame)
        btn_f.pack(fill="x", pady=(10, 5))
        ttk.Button(btn_f, text="＋ 追加", width=8, command=self.add_drone_entry).pack(side="left", padx=2)
        ttk.Button(btn_f, text="－ 削除", width=8, command=self.remove_drone_entry).pack(side="left", padx=2)
        ttk.Button(btn_f, text="設定保存", command=self.save_config).pack(side="right", padx=2)

        self.connect_wifi_btn = ttk.Button(ip_frame, text="📡 Wi-Fi接続 (IP設定後)", command=self.auto_connect_wifi)
        self.connect_wifi_btn.pack(fill="x", pady=(5, 0))

    def _create_project_selection_section(self, parent):
        file_frame = ttk.LabelFrame(parent, text="② プロジェクト", padding="10")
        file_frame.pack(fill="x", pady=(0, 15))
        self.sb3_path_label = ttk.Label(file_frame, text="ファイルが選択されていません", wraplength=300)
        self.sb3_path_label.pack(fill="x", pady=(0, 10))
        ttk.Button(file_frame, text="📂 Scratchファイルを開く", command=self.select_file).pack(fill="x", pady=(0, 5))
        self.parse_btn = ttk.Button(file_frame, text="🔄 タイムラインを解析", command=self.parse_project, state="disabled")
        self.parse_btn.pack(fill="x", pady=(0, 5))
        self.timeline_viewer_btn = ttk.Button(file_frame, text="📊 タイムライン詳細", command=self.open_timeline_viewer, state="disabled")
        self.timeline_viewer_btn.pack(fill="x", pady=(0, 5))

    def _create_audio_selection_section(self, parent):
        audio_frame = ttk.LabelFrame(parent, text="③ 音源設定 (任意)", padding="10")
        audio_frame.pack(fill="x", pady=(0, 15))
        self.audio_path_label = ttk.Label(audio_frame, text="未選択", foreground="gray", wraplength=300)
        self.audio_path_label.pack(fill="x", pady=(0,5))
        ttk.Button(audio_frame, text="🎵 音楽リスト管理", command=self.open_music_manager).pack(fill="x")

    def _create_show_control_section(self, parent):
        action_frame = ttk.LabelFrame(parent, text="④ ショー実行", padding="10")
        action_frame.pack(fill="x", pady=(0, 15))
        self.connect_btn = ttk.Button(action_frame, text="🔗 ドローンへ接続 (SDK)", command=self.connect_drones, state="disabled")
        self.connect_btn.pack(fill="x", pady=(0, 5))
        self.start_btn = ttk.Button(action_frame, text="▶ ショーを開始", command=self.start_show, state="disabled", style="Accent.TButton")
        self.start_btn.pack(fill="x", pady=(5, 5))
        self.stop_btn = ttk.Button(action_frame, text="⏹ 緊急停止", command=self.emergency_stop, state="disabled", style="Stop.TButton")
        self.stop_btn.pack(fill="x", pady=(5, 0))

    def _create_status_bar(self, parent):
        status_bar = ttk.Frame(parent, padding=(5, 5))
        status_bar.grid(row=0, column=1, sticky="ew", pady=(0, 5))
        ttk.Label(status_bar, text="ステータス:", style="Header.TLabel").pack(side="left")
        ttk.Label(status_bar, textvariable=self.show_status).pack(side="left", padx=5)

    def _create_log_panels(self, parent):
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        log_pane = ttk.PanedWindow(right_frame, orient="vertical")
        log_pane.pack(fill="both", expand=True)
        
        timeline_frame = ttk.Frame(log_pane)
        log_pane.add(timeline_frame, weight=1)
        ttk.Label(timeline_frame, text="タイムライン / 実行ログ", style="Header.TLabel").pack(anchor="w", padx=5)
        self.schedule_text = scrolledtext.ScrolledText(timeline_frame, state="disabled", wrap="none", height=15, font=FONT_MONOSPACE)
        self.schedule_text.pack(expand=True, fill="both", padx=5, pady=5)
        
        log_frame = ttk.Frame(log_pane)
        log_pane.add(log_frame, weight=1)
        ttk.Label(log_frame, text="システム通信ログ", style="Header.TLabel").pack(anchor="w", padx=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, state="disabled", wrap="none", height=10, font=FONT_MONOSPACE)
        self.log_text.pack(expand=True, fill="both", padx=5, pady=5)
        self._configure_text_tags()

    def _configure_text_tags(self):
        for widget in [self.log_text, self.schedule_text]:
            widget.tag_config("INFO", foreground="black")
            widget.tag_config("SUCCESS", foreground=COLOR_SUCCESS)
            widget.tag_config("WARNING", foreground=COLOR_WARNING)
            widget.tag_config("ERROR", foreground=COLOR_ERROR)
            widget.tag_config("HEADER", foreground=COLOR_PRIMARY, font=FONT_HEADER)
            widget.tag_config("HIGHLIGHT", background=COLOR_HIGHLIGHT)
            widget.tag_config("TAKEOFF", foreground=COLOR_SUCCESS, font=(FONT_MONOSPACE[0], FONT_MONOSPACE[1], "bold"))
            widget.tag_config("LAND", foreground=COLOR_DANGER, font=(FONT_MONOSPACE[0], FONT_MONOSPACE[1], "bold"))

    # ==========================================
    # ★ 全自動セットアップ（安全版）
    # ==========================================
    def full_auto_setup(self):
        if not NetworkManager:
            messagebox.showerror("エラー", "NetworkManagerが見つかりません")
            return

        nm = NetworkManager()
        # rawインターフェース情報取得（SSIDを見るため）
        raw_interfaces = nm._get_wifi_interfaces()
        
        if not raw_interfaces:
            messagebox.showerror("エラー", "Wi-Fiアダプタが見つかりません。")
            return

        # フィルタリング
        target_interfaces = []
        skipped_interfaces = []

        for iface in raw_interfaces:
            name = iface['name']
            ssid = iface['ssid']
            
            # 家のWi-Fi (TELLO以外に接続中) なら除外
            if ssid == "" or ssid.upper().startswith("TELLO-"):
                target_interfaces.append(name)
            else:
                skipped_interfaces.append(f"{name} (接続中: {ssid})")

        msg = "【IPアドレス自動固定設定】\n\n"
        if skipped_interfaces:
            msg += "⚠️ 以下の安全なアダプタ（家のWi-Fi等）は無視します:\n"
            for s in skipped_interfaces:
                msg += f"  ・ {s}\n"
            msg += "\n"
            
        if not target_interfaces:
            msg += "❌ 設定可能なTello用アダプタが見つかりませんでした。\nドングルがPCに認識されているか、他のWi-Fiに繋がっていないか確認してください。"
            messagebox.showwarning("中断", msg)
            return

        msg += "✅ 以下のドングルにIPアドレスを割り当てます:\n"
        base_ip = [192, 168, 10, 2]
        assignments = []
        for i, name in enumerate(target_interfaces):
            ip = f"{base_ip[0]}.{base_ip[1]}.{base_ip[2]}.{base_ip[3] + i}"
            msg += f"  ・ {name}  ->  {ip}\n"
            assignments.append((name, ip))

        msg += "\n実行してよろしいですか？\n(※管理者権限が必要です)"

        if not messagebox.askyesno("実行確認", msg):
            return

        # 実行
        self.log({"message": "--- 安全セットアップ開始 ---", "level": "INFO"})
        while self.drone_entry_widgets: self.remove_drone_entry()
        
        success_count = 0
        for i, (iface, ip) in enumerate(assignments):
            drone_name = f"Tello_{chr(65 + i)}"
            self.log({"message": f"設定中: {iface} -> {ip}..."})
            
            if nm.set_static_ip(iface, ip):
                self.log({"message": f"成功: {iface}", "level": "SUCCESS"})
                self.add_drone_entry(drone_name, ip, label_text=f"{drone_name} ({iface}):")
                success_count += 1
            else:
                self.log({"message": f"失敗: {iface}", "level": "ERROR"})
                self.add_drone_entry(drone_name, "", label_text=f"{drone_name} (失敗):")

        messagebox.showinfo("完了", f"{success_count}台の設定が完了しました。")

    # --- 以下、既存機能 ---
    def add_drone_entry(self, name=None, ip="", label_text=None):
        count = len(self.drone_entry_widgets)
        if name is None: name = f"Tello_{chr(65 + count)}"
        if label_text is None: label_text = f"{name}:"
        
        widget_dict = {}
        row_frame = ttk.Frame(self.ip_entry_frame)
        row_frame.pack(fill="x", pady=2)
        
        ttk.Label(row_frame, text=label_text, width=25).pack(side="left", padx=(0, 5))
        entry = ttk.Entry(row_frame)
        entry.pack(side="left", expand=True, fill="x", padx=(0,5))
        entry.insert(0, ip)
        
        telemetry = ttk.Label(row_frame, text="---", width=10, foreground="gray")
        telemetry.pack(side="left")
        
        widget_dict.update({"name": name, "frame": row_frame, "ip_widget": entry, "telemetry": telemetry})
        self.drone_entry_widgets.append(widget_dict)

    def remove_drone_entry(self):
        if not self.drone_entry_widgets: return
        w = self.drone_entry_widgets.pop()
        w["frame"].destroy()

    def auto_connect_wifi(self):
        if not NetworkManager: return
        threading.Thread(target=lambda: NetworkManager().connect_all_tellos(lambda m: self.log({"message": m}))).start()

    def select_file(self):
        path = filedialog.askopenfilename(title="Scratchプロジェクトを選択", filetypes=[("Scratch Project", "*.sb3")])
        if path:
            self.sb3_path.set(path)
            self.sb3_path_label.configure(text=path.split("/")[-1])
            self.parse_btn["state"] = "normal"

    def parse_project(self):
        self.log({"level": "INFO", "message": "解析中..."})
        parser = ScratchProjectParser(self.sb3_path.get(), self.log_queue)
        self.schedule, self.total_time = parser.parse_to_schedule()
        if self.schedule:
            self.log({"level": "SUCCESS", "message": f"解析完了 (予想: {self.total_time:.1f}秒)"})
            self.connect_btn["state"] = "normal"
            self.timeline_viewer_btn["state"] = "normal"
            self._display_timeline()
        else:
            self.log({"level": "ERROR", "message": "解析失敗"})

    def _display_timeline(self):
        self.schedule_text.config(state="normal")
        self.schedule_text.delete(1.0, tk.END)
        self.time_to_line_map = {}
        current_line = 1
        for evt in self.schedule:
            time = evt['time']
            start_line = current_line
            tag = "INFO"
            if evt.get('type') == 'TAKEOFF': tag = "TAKEOFF"
            elif evt.get('type') == 'LAND': tag = "LAND"
            
            msg = f"{time:>6.2f}s | {evt.get('target','ALL'):<8} | {evt.get('type','CMD')} : {evt.get('command') or evt.get('text')}\n"
            self.schedule_text.insert(tk.END, msg, tag)
            current_line += 1
            if time not in self.time_to_line_map:
                self.time_to_line_map[time] = {"start": start_line, "end": current_line-1}
        self.schedule_text.config(state="disabled")

    def connect_drones(self):
        conf = [{'name': w['name'], 'pc_ip': w['ip_widget'].get()} for w in self.drone_entry_widgets if w['ip_widget'].get()]
        if not conf:
            messagebox.showerror("エラー", "IPアドレス設定なし")
            return
        threading.Thread(target=lambda: ShowRunner(conf, self.schedule, self.stop_event, self.log_queue, self.total_time).connect()).start()

    def start_show(self):
        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"
        self.stop_event.clear()
        if self.music_list:
            self.music_player.set_music_list(self.music_list)
            self.music_player.play_medley(delay_seconds=3.0)
        runner = ShowRunner(None, self.schedule, self.stop_event, self.log_queue, self.total_time, self.controllers)
        runner.set_music_player(self.music_player)
        self.show_thread = threading.Thread(target=runner.run_show, daemon=True)
        self.show_thread.start()

    def emergency_stop(self):
        self.stop_event.set()
        self.music_player.stop()
        self.stop_btn["state"] = "disabled"
        self.log({"level": "ERROR", "message": "!!! 緊急停止 !!!"})

    def open_music_manager(self):
        MusicManagerWindow(self.master, self.music_player, self.music_list, self._on_music_saved)

    def open_timeline_viewer(self):
        if self.schedule:
            TimelineViewerWindow(self.master, self.schedule, self.total_time, self.music_list, self.music_player)

    def _on_music_saved(self, m_list, interval, yt_titles=None, bpm=None):
        self.music_list = m_list
        self.music_player.set_interval(interval)
        if m_list: self.audio_path_label.config(text=f"セットリスト: {len(m_list)}曲", foreground=COLOR_SUCCESS)
        else: self.audio_path_label.config(text="未選択", foreground="gray")

    def log(self, item): self.log_queue.put(item)

    def process_log_queue(self):
        while not self.log_queue.empty():
            item = self.log_queue.get_nowait()
            if isinstance(item, dict):
                msg_type = item.get("type")
                if msg_type == "connection_success":
                    self.controllers = item["controllers"]
                    self.start_btn["state"] = "normal"
                    self.connect_btn.config(text="✓ 接続済み")
                    continue
                elif msg_type == "highlight":
                    self.update_timeline_highlight(item.get("time"))
                    continue
                elif msg_type == "clear_highlight":
                    self.update_timeline_highlight(None)
                    continue
                elif msg_type == "show_finished":
                    self.start_btn["state"] = "disabled"
                    self.stop_btn["state"] = "disabled"
                    self.connect_btn.config(text="🔗 ドローンへ接続")
                    self.connect_btn["state"] = "normal"
                    continue
                
                msg = item.get("message", "")
                lvl = item.get("level", "INFO")
                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, f"{msg}\n", lvl)
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")
        self.master.after(100, self.process_log_queue)

    def update_timeline_highlight(self, time):
        self.schedule_text.config(state="normal")
        self.schedule_text.tag_remove("HIGHLIGHT", "1.0", tk.END)
        if time is not None and time in self.time_to_line_map:
            lines = self.time_to_line_map[time]
            self.schedule_text.tag_add("HIGHLIGHT", f"{lines['start']}.0", f"{lines['end']}.end")
            self.schedule_text.see(f"{lines['start']}.0")
        self.schedule_text.config(state="disabled")

    def _update_telemetry_loop(self):
        for w in self.drone_entry_widgets:
            name = w['name']
            if name in self.controllers:
                st = self.controllers[name].get_state()
                w['telemetry'].config(text=f"BAT:{st['bat']}%", foreground="green" if st['active'] else "red")
        self.master.after(1000, self._update_telemetry_loop)

    def load_config(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                c = json.load(f)
                while self.drone_entry_widgets: self.remove_drone_entry()
                for k, v in c.items(): self.add_drone_entry(k, v)
        except: self.add_drone_entry()

    def save_config(self):
        d = {w['name']: w['ip_widget'].get() for w in self.drone_entry_widgets}
        with open(CONFIG_FILE, 'w') as f: json.dump(d, f, indent=4)
        messagebox.showinfo("成功", "設定を保存しました。")

    def on_closing(self):
        if self.show_thread and self.show_thread.is_alive(): self.emergency_stop()
        self.master.destroy()