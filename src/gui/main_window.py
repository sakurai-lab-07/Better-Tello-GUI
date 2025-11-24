"""
メインGUIウィンドウ
（シミュレーター削除・軽量化版）
"""

import sys
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from queue import Queue

# coreフォルダをパスに追加
sys.path.append('.')

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

# coreパッケージからのインポート
try:
    from core.scratch_parser import ScratchProjectParser
    from core.show_runner import ShowRunner
    from core.network_manager import NetworkManager
    from core.music_player import MusicPlayer
except ImportError:
    # フォールバック
    from scratch_parser import ScratchProjectParser
    from show_runner import ShowRunner
    from music_player import MusicPlayer
    try:
        from network_manager import NetworkManager
    except ImportError:
        NetworkManager = None

from .music_manager_window import MusicManagerWindow
from .timeline_viewer_window import TimelineViewerWindow


class TelloApp:
    """メインGUIアプリケーションクラス"""

    def __init__(self, master):
        self.master = master
        self.master.title("Tello Scratch ドローンショー・コントローラー")
        self.master.geometry("1050x850")
        self.master.minsize(900, 800)
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
        self.monitoring = True

        # 変数
        self.sb3_path = tk.StringVar()
        self.show_status = tk.StringVar(value="準備完了")
        self.log_queue = Queue()
        self.show_thread = None
        self.stop_event = threading.Event()
        self.controllers = {}

        # 音楽管理
        self.music_player = MusicPlayer(self.log_queue)
        self.music_list = []

        # UI作成
        self._create_widgets()
        self.load_config()
        
        # 処理開始
        self.process_log_queue()
        self._update_telemetry_loop()

    def _configure_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure(".", background=COLOR_BACKGROUND, foreground="black", font=self.font_normal)
        s.configure("TFrame", background=COLOR_BACKGROUND)
        s.configure("TLabel", background=COLOR_BACKGROUND, foreground="black")
        s.configure("Header.TLabel", font=self.font_header, foreground=COLOR_ACCENT)
        s.configure("TLabelframe", background=COLOR_BACKGROUND)
        s.configure("TLabelframe.Label", font=self.font_bold_large, foreground="#333")
        s.configure("TButton", font=self.font_normal, padding=6)
        s.configure("Accent.TButton", font=self.font_normal, padding=8, foreground="white", background=COLOR_ACCENT)
        s.map("Accent.TButton", background=[('active', COLOR_ACCENT_HOVER), ('disabled', '#8abadd')])
        s.configure("Stop.TButton", font=self.font_normal, padding=8, foreground="white", background=COLOR_STOP)
        s.map("Stop.TButton", background=[('active', COLOR_STOP_HOVER), ('disabled', '#e89c9f')])
        s.configure("BatteryOK.TLabel", foreground="green", font=self.font_header)
        s.configure("BatteryLow.TLabel", foreground="red", font=self.font_header)
        s.configure("BatteryOffline.TLabel", foreground="gray", font=self.font_normal)

    def _create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 15))
        
        # --- ① ドローン設定 ---
        ip_frame = ttk.LabelFrame(left_frame, text="① ドローンの設定 (テレメトリ)", padding="10")
        ip_frame.pack(fill="x", pady=(0, 15))
        
        header_frame = ttk.Frame(ip_frame)
        header_frame.pack(fill="x", pady=(0, 2))
        ttk.Label(header_frame, text="機体名 / SSID", width=18).pack(side="left")
        ttk.Label(header_frame, text="IPアドレス", width=15).pack(side="left", padx=5)
        ttk.Label(header_frame, text="BAT / 高度", width=12).pack(side="left", padx=5)
        
        self.ip_entry_frame = ttk.Frame(ip_frame)
        self.ip_entry_frame.pack(fill="x")
        
        ip_button_frame = ttk.Frame(ip_frame)
        ip_button_frame.pack(fill="x", pady=(10, 5))
        
        ttk.Button(ip_button_frame, text="＋ 追加", command=self.add_drone_entry).pack(side="left", expand=True, fill="x", padx=(0,2))
        ttk.Button(ip_button_frame, text="－ 削除", command=self.remove_drone_entry).pack(side="left", expand=True, fill="x", padx=(2,2))
        ttk.Button(ip_button_frame, text="📡 Wi-Fi接続", command=self.auto_connect_wifi).pack(side="left", expand=True, fill="x", padx=(2,2))
        ttk.Button(ip_button_frame, text="🔍 IP検出", command=self.auto_detect_drones).pack(side="left", expand=True, fill="x", padx=(2,0))
        
        ttk.Button(ip_frame, text="⚙️ 設定を保存", command=self.save_config).pack(fill="x", pady=(10,0))
        
        # --- ② プロジェクト ---
        file_frame = ttk.LabelFrame(left_frame, text="② プロジェクト", padding="10")
        file_frame.pack(fill="x", pady=(0,15))
        self.sb3_path_label = ttk.Label(file_frame, text="ファイル未選択", wraplength=230)
        self.sb3_path_label.pack(fill="x", pady=(0, 10))
        ttk.Button(file_frame, text="📂 Scratchファイルを開く", command=self.select_file).pack(fill="x", pady=(0,5))
        self.parse_btn = ttk.Button(file_frame, text="🔄 タイムラインを解析", command=self.parse_scratch_project, state="disabled")
        self.parse_btn.pack(fill="x")

        # --- ③ 音楽・演出 ---
        music_frame = ttk.LabelFrame(left_frame, text="③ 音楽・演出", padding="10")
        music_frame.pack(fill="x", pady=(0, 15))
        self.music_info_label = ttk.Label(music_frame, text="音楽未設定", wraplength=230)
        self.music_info_label.pack(fill="x", pady=(0, 10))
        btn_grid = ttk.Frame(music_frame)
        btn_grid.pack(fill="x")
        ttk.Button(btn_grid, text="🎵 音楽管理", command=self.open_music_manager).pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.timeline_btn = ttk.Button(btn_grid, text="📊 タイムライン", command=self.open_timeline_viewer, state="disabled")
        self.timeline_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))
        
        # --- ④ ショー実行 ---
        action_frame = ttk.LabelFrame(left_frame, text="④ ショー実行", padding="10")
        action_frame.pack(fill="x", pady=(0,15))
        self.connect_btn = ttk.Button(action_frame, text="📡 ドローンに接続", command=self.connect_drones, state="disabled")
        self.connect_btn.pack(fill="x", pady=(0, 5))
        self.start_btn = ttk.Button(action_frame, text="▶️ ショーを開始", command=self.start_show, state="disabled", style="Accent.TButton")
        self.start_btn.pack(fill="x", pady=(5, 5))
        self.stop_btn = ttk.Button(action_frame, text="⏹️ 緊急停止", command=self.emergency_stop, state="disabled", style="Stop.TButton")
        self.stop_btn.pack(fill="x", pady=(5, 0))
        
        # 右カラム
        status_bar = ttk.Frame(main_frame, padding=(5,5))
        status_bar.grid(row=0, column=1, sticky="ew", pady=(0,5))
        ttk.Label(status_bar, text="ステータス:", style="Header.TLabel").pack(side="left")
        ttk.Label(status_bar, textvariable=self.show_status).pack(side="left", padx=5)
        
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        
        log_pane = ttk.PanedWindow(right_frame, orient="horizontal")
        log_pane.pack(fill="both", expand=True)
        
        timeline_frame = ttk.Frame(log_pane)
        log_pane.add(timeline_frame, weight=1)
        ttk.Label(timeline_frame, text="解析ログ", style="Header.TLabel").pack(anchor="w", padx=5)
        self.schedule_text = scrolledtext.ScrolledText(timeline_frame, state="disabled", wrap="none", height=10, font=self.font_monospace)
        self.schedule_text.pack(expand=True, fill="both", padx=5, pady=(0,5))
        
        log_frame = ttk.Frame(log_pane)
        log_pane.add(log_frame, weight=1)
        ttk.Label(log_frame, text="通信ログ", style="Header.TLabel").pack(anchor="w", padx=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, state="disabled", wrap="none", height=10, font=self.font_monospace)
        self.log_text.pack(expand=True, fill="both", padx=5, pady=(0,5))
        
        self._configure_text_tags()

    def _configure_text_tags(self):
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("SUCCESS", foreground=COLOR_SUCCESS)
        self.log_text.tag_config("WARNING", foreground=COLOR_WARNING)
        self.log_text.tag_config("ERROR", foreground=COLOR_ERROR)
        self.schedule_text.tag_config("TAKEOFF", foreground=COLOR_SUCCESS, font=(self.font_monospace[0], self.font_monospace[1], 'bold'))
        self.schedule_text.tag_config("INFO", foreground="black")
        self.schedule_text.tag_config("WAIT", foreground="blue")
        self.schedule_text.tag_config("WARNING", foreground=COLOR_ERROR)
        self.schedule_text.tag_config("HEADER", foreground=COLOR_ACCENT, font=self.font_header)
        self.schedule_text.tag_config("HIGHLIGHT", background=COLOR_HIGHLIGHT)
        self.schedule_text.tag_config("LAND", foreground=COLOR_STOP, font=(self.font_monospace[0], self.font_monospace[1], 'bold'))

    def add_drone_entry(self, name=None, ip=''):
        drone_count = len(self.drone_entry_widgets)
        if name is None: name = f'Tello_{chr(65 + drone_count)}'
        widget_dict = {}
        row_frame = ttk.Frame(self.ip_entry_frame)
        row_frame.pack(fill="x", pady=2)
        label = ttk.Label(row_frame, text=f"{name}:", width=18)
        label.pack(side="left", padx=(0,5))
        entry = ttk.Entry(row_frame, width=15)
        entry.pack(side="left", padx=(0,5))
        entry.insert(0, ip)
        telemetry_label = ttk.Label(row_frame, text="--- / ---", width=12, style="BatteryOffline.TLabel")
        telemetry_label.pack(side="left", padx=5)
        widget_dict.update({'name': name, 'frame': row_frame, 'ip_widget': entry, 'label_widget': label, 'telemetry_widget': telemetry_label})
        self.drone_entry_widgets.append(widget_dict)

    def remove_drone_entry(self):
        if not self.drone_entry_widgets: return
        widgets_to_remove = self.drone_entry_widgets.pop()
        widgets_to_remove['frame'].destroy()

    def _update_telemetry_loop(self):
        if not self.monitoring: return
        try:
            if self.controllers:
                for widget in self.drone_entry_widgets:
                    name = widget['name']
                    label = widget['telemetry_widget']
                    if name in self.controllers:
                        state = self.controllers[name].get_state()
                        if state['active']:
                            bat = state['bat']
                            height = state['h']
                            text = f"BAT:{bat}% H:{height}cm"
                            if bat < 20: label.config(text=text, style="BatteryLow.TLabel")
                            else: label.config(text=text, style="BatteryOK.TLabel")
                        else:
                            label.config(text="OFFLINE", style="BatteryOffline.TLabel")
                    else:
                        label.config(text="---", style="BatteryOffline.TLabel")
        except Exception: pass
        self.master.after(1000, self._update_telemetry_loop)

    def auto_connect_wifi(self):
        if NetworkManager is None:
             messagebox.showerror("エラー", "NetworkManagerモジュールが読み込めませんでした。")
             return
        if not messagebox.askyesno("Wi-Fi自動接続", "Wi-Fi自動接続を開始しますか？"): return
        self.show_status.set("Wi-Fi接続処理中...")
        self.connect_btn['state'] = 'disabled'
        threading.Thread(target=self._auto_connect_worker).start()

    def _auto_connect_worker(self):
        nm = NetworkManager()
        def log_cb(msg): self.log({"level": "INFO", "message": msg})
        try:
            self.log({"level": "INFO", "message": "--- Wi-Fi自動接続プロセス開始 ---"})
            connected_list = nm.connect_all_tellos(log_callback=log_cb)
            if connected_list:
                self.log({"level": "SUCCESS", "message": f"{len(connected_list)} 台接続。IP取得待ち..."})
                for i in range(10, 0, -1):
                    self.show_status.set(f"IPアドレス取得待機中... {i}")
                    time.sleep(1)
                self.show_status.set("接続処理完了。IP検出を実行してください。")
                messagebox.showinfo("接続完了", "接続完了。IP検出ボタンを押してください。")
            else:
                self.log({"level": "WARNING", "message": "Telloが見つかりませんでした。"})
                self.show_status.set("接続失敗")
        except Exception as e:
            self.log({"level": "ERROR", "message": f"Wi-Fi接続エラー: {e}"})

    def auto_detect_drones(self):
        if NetworkManager is None:
             messagebox.showerror("エラー", "NetworkManagerがありません。")
             return
        nm = NetworkManager()
        found = nm.get_connected_tellos()
        if not found:
            messagebox.showwarning("失敗", "Telloが見つかりません。")
            return
        if self.drone_entry_widgets:
             if not messagebox.askyesno("確認", "リストを上書きしますか？"): return
             while self.drone_entry_widgets: self.remove_drone_entry()
        for i, t in enumerate(found):
            name = f"Tello_{chr(65 + i)}"
            self.add_drone_entry(name=name, ip=t['ip'])
            self.drone_entry_widgets[-1]['label_widget'].config(text=f"{name} ({t['ssid']}):")
            self.log({"level": "SUCCESS", "message": f"検出: {name} -> {t['ip']}"})
        messagebox.showinfo("完了", f"{len(found)}台設定しました。")

    def load_config(self):
        try:
            with open(CONFIG_FILE, 'r') as f: config = json.load(f)
            while self.drone_entry_widgets: self.remove_drone_entry()
            for name, ip in config.items(): self.add_drone_entry(name=name, ip=ip)
            self.log({"level": "INFO", "message": "設定読み込み完了"})
        except:
            if not self.drone_entry_widgets: self.add_drone_entry()

    def save_config(self):
        data = {w['name']: w['ip_widget'].get() for w in self.drone_entry_widgets}
        try:
            with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)
            self.log({"level": "INFO", "message": "設定保存完了"})
            messagebox.showinfo("成功", "保存しました。")
        except Exception as e:
            messagebox.showerror("エラー", f"保存失敗: {e}")

    def select_file(self):
        path = filedialog.askopenfilename(filetypes=[("Scratch Project", "*.sb3")])
        if path:
            self.sb3_path.set(path)
            self.sb3_path_label.configure(text=path.split('/')[-1])
            self._reset_ui_to_file_selected_state()

    def open_music_manager(self):
        MusicManagerWindow(self.master, self.music_player, self.music_list, self.on_music_list_saved)

    def on_music_list_saved(self, new_list, interval):
        self.music_list = new_list
        self.music_player.set_music_list(new_list)
        self.music_player.set_interval(interval)
        self.music_info_label.config(text=f"設定済み: {len(new_list)}曲", foreground=COLOR_SUCCESS)

    def open_timeline_viewer(self):
        if not self.schedule: return
        TimelineViewerWindow(self.master, self.music_list, self.schedule, self.total_time, self.music_player.get_interval())

    def parse_scratch_project(self):
        path = self.sb3_path.get()
        if not path: return
        
        parser = ScratchProjectParser(path, self.log_queue)
        self.schedule, self.total_time = parser.parse_to_schedule()
        
        self.schedule_text.config(state="normal")
        self.schedule_text.delete(1.0, tk.END)
        self.time_to_line_map = {}
        
        if self.schedule:
            self.schedule_text.insert(tk.END, f"--- 解析完了 (総時間: {self.total_time:.2f}s) ---\n", "HEADER")
            current_line = 2
            
            times = sorted(list(set(e['time'] for e in self.schedule)))
            for t in times:
                evts = [e for e in self.schedule if e['time'] == t]
                start = current_line
                for e in evts:
                    cmd_str = e.get('command', '')
                    type_str = e.get('type', 'INFO')
                    
                    if type_str == 'TAKEOFF':
                        msg = f"{t:>6.2f}s | {e['target']:<8} | 離陸\n"
                    elif type_str == 'LAND':
                        msg = f"{t:>6.2f}s | {e['target']:<8} | 着陸\n"
                    elif type_str == 'WAIT':
                        msg = f"{t:>6.2f}s | {e['target']:<8} | 待機 {e.get('text', '')}\n"
                    elif type_str == 'COMMAND':
                        msg = f"{t:>6.2f}s | {e['target']:<8} | 実行: {cmd_str}\n"
                    else:
                        msg = f"{t:>6.2f}s | {e.get('target',''):<8} | {type_str}\n"
                    
                    self.schedule_text.insert(tk.END, msg, type_str)
                    current_line += 1
                self.time_to_line_map[t] = {'start': start, 'end': current_line-1}
            
            self.connect_btn['state'] = 'normal'
            self.timeline_btn['state'] = 'normal'
            self.show_status.set("解析完了")
        else:
            self.schedule_text.insert(tk.END, "解析失敗\n", "ERROR")
        self.schedule_text.config(state="disabled")

    def connect_drones(self):
        self.connect_btn['state'] = 'disabled'
        self.show_status.set("接続中...")
        config = []
        for w in self.drone_entry_widgets:
            ip = w['ip_widget'].get()
            if ip: config.append({'name': w['name'], 'pc_ip': ip})
        if not config:
            self.connect_btn['state'] = 'normal'
            return
        threading.Thread(target=self._connect_worker, args=(config,)).start()

    def _connect_worker(self, config):
        runner = ShowRunner(config, self.schedule, self.stop_event, self.log_queue, self.total_time)
        runner.connect()

    def start_show(self):
        low_battery = []
        if self.controllers:
            for name, ctrl in self.controllers.items():
                st = ctrl.get_state()
                if st['active'] and st['bat'] < 20: low_battery.append(f"{name} ({st['bat']}%)")
        if low_battery:
            messagebox.showerror("離陸ロック", "バッテリー不足:\n" + "\n".join(low_battery))
            return

        self._set_ui_for_show_running(True)
        self.stop_event.clear()
        runner = ShowRunner(None, self.schedule, self.stop_event, self.log_queue, self.total_time, self.controllers)
        if hasattr(runner, 'set_music_player'): runner.set_music_player(self.music_player)
        else: runner.music_player = self.music_player
        self.show_thread = threading.Thread(target=runner.run_show)
        self.show_thread.start()

    def emergency_stop(self):
        self.stop_event.set()
        self.music_player.stop()
        self.show_status.set("緊急停止")
        self.stop_btn['state'] = 'disabled'

    def _reset_ui_to_parsed_state(self):
        self.controllers = {}
        self.stop_event.clear()
        self.stop_btn['state'] = 'disabled'
        self.start_btn['state'] = 'disabled'
        self.connect_btn['state'] = 'normal'
        self.show_status.set("準備完了")
        self.update_timeline_highlight(None)

    def _set_ui_for_show_running(self, running):
        state = 'disabled' if running else 'normal'
        self.start_btn['state'] = state
        self.parse_btn['state'] = state
        self.connect_btn['state'] = state
        self.stop_btn['state'] = 'normal' if running else 'disabled'

    def _reset_ui_to_file_selected_state(self):
        self.parse_btn['state'] = 'normal'
        self.connect_btn['state'] = 'disabled'
        self.start_btn['state'] = 'disabled'

    def log(self, item): self.log_queue.put(item)

    def process_log_queue(self):
        try:
            while not self.log_queue.empty():
                item = self.log_queue.get_nowait()
                if isinstance(item, dict) and 'type' in item:
                    t = item['type']
                    if t == 'highlight': self.update_timeline_highlight(item.get('time'))
                    elif t == 'clear_highlight': self.update_timeline_highlight(None)
                    elif t == 'connection_success':
                        self.controllers = item['controllers']
                        self.start_btn['state'] = 'normal'
                        self.connect_btn.config(text="✓ 接続済み")
                        self.show_status.set("接続完了")
                    elif t == 'connection_fail':
                        self.connect_btn['state'] = 'normal'
                        self.show_status.set("接続失敗")
                    elif t == 'show_finished': self._reset_ui_to_parsed_state()
                    continue
                
                msg = item.get('message', '') if isinstance(item, dict) else str(item)
                lvl = item.get('level', 'INFO') if isinstance(item, dict) else 'INFO'
                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, msg + '\n', lvl)
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")
        finally:
            self.master.after(100, self.process_log_queue)

    def update_timeline_highlight(self, t):
        self.schedule_text.config(state="normal")
        if self.last_highlighted_lines:
            self.schedule_text.tag_remove("HIGHLIGHT", f"{self.last_highlighted_lines['start']}.0", f"{self.last_highlighted_lines['end']}.end")
        if t is not None and t in self.time_to_line_map:
            info = self.time_to_line_map[t]
            self.schedule_text.tag_add("HIGHLIGHT", f"{info['start']}.0", f"{info['end']}.end")
            self.schedule_text.see(f"{info['start']}.0")
            self.last_highlighted_lines = info
        self.schedule_text.config(state="disabled")

    def on_closing(self):
        if self.show_thread and self.show_thread.is_alive():
            if messagebox.askyesno("終了", "ショー停止して終了しますか？"):
                self.emergency_stop()
                self.master.destroy()
        else:
            self.master.destroy()