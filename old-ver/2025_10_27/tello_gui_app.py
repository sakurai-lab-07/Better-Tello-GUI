import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from queue import Queue
import threading

from scratch_parser import ScratchProjectParser
from show_runner import ShowRunner

class TelloApp:
    def __init__(self, master):
        self.master = master; self.master.title("Tello Scratch ドローンショー・コントローラー (最終安定版)"); self.master.geometry("900x700"); self.master.minsize(800, 600)
        
        self.setup_styles()

        self.drone_entry_widgets = []; self.schedule = None; self.total_time = 0.0; self.time_to_line_map = {}; self.last_highlighted_lines = None
        self.sb3_path = tk.StringVar(); self.audio_path = tk.StringVar()
        self.show_status = tk.StringVar(value="準備完了"); self.log_queue = Queue(); self.show_thread = None; self.stop_event = threading.Event()
        self.controllers = {}
        
        self._create_widgets()
        self.load_config()
        self.process_log_queue()

    def setup_styles(self):
        self.font_normal = ("Yu Gothic UI", 10); self.font_bold_large = ("Yu Gothic UI", 12, "bold"); self.font_header = ("Yu Gothic UI", 10, "bold"); self.font_monospace = ("Consolas", 10)
        s = ttk.Style(); s.theme_use('clam'); s.configure(".", background="#f0f0f0", foreground="black", font=self.font_normal); s.configure("TFrame", background="#f0f0f0"); s.configure("TLabel", background="#f0f0f0", foreground="black"); s.configure("Header.TLabel", font=self.font_header, foreground="#0078D7"); s.configure("TLabelframe", background="#f0f0f0"); s.configure("TLabelframe.Label", font=self.font_bold_large, foreground="#333"); s.configure("TButton", font=self.font_normal, padding=6); s.configure("Accent.TButton", font=self.font_normal, padding=8, foreground="white", background="#0078D7"); s.map("Accent.TButton", background=[('active', '#005f9e'), ('disabled', '#5a9fd4')]); s.configure("Stop.TButton", font=self.font_normal, padding=8, foreground="white", background="#d13438"); s.map("Stop.TButton", background=[('active', '#a4262c'), ('disabled', '#e89c9f')])

    def _create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="15"); main_frame.pack(fill="both", expand=True); main_frame.grid_rowconfigure(1, weight=1); main_frame.grid_columnconfigure(1, weight=1)
        left_frame = ttk.Frame(main_frame); left_frame.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 15));
        
        # ① ドローン設定
        ip_frame = ttk.LabelFrame(left_frame, text="① ドローンの設定", padding="10"); ip_frame.pack(fill="x", pady=(0, 15))
        self.ip_entry_frame = ttk.Frame(ip_frame); self.ip_entry_frame.pack(fill="x")
        ip_button_frame = ttk.Frame(ip_frame); ip_button_frame.pack(fill="x", pady=(10, 5))
        ttk.Button(ip_button_frame, text="＋ 追加", command=self.add_drone_entry).pack(side="left", expand=True, fill="x", padx=(0,2))
        ttk.Button(ip_button_frame, text="－ 削除", command=self.remove_drone_entry).pack(side="left", expand=True, fill="x", padx=(2,0))
        ttk.Button(ip_frame, text="⚙️ 設定を保存", command=self.save_config).pack(fill="x", pady=(10,0))
        
        # ② プロジェクト選択 & 解析
        file_frame = ttk.LabelFrame(left_frame, text="② プロジェクト選択 & 解析", padding="10"); file_frame.pack(fill="x", pady=(0,15))
        self.sb3_path_label = ttk.Label(file_frame, text="ファイルが選択されていません", wraplength=230); self.sb3_path_label.pack(fill="x", pady=(0, 10))
        ttk.Button(file_frame, text="📂 Scratchファイルを開く", command=self.select_file).pack(fill="x", pady=(0,5))
        self.parse_btn = ttk.Button(file_frame, text="🔄 タイムラインを解析", command=self.parse_scratch_project, state="disabled"); self.parse_btn.pack(fill="x")

        # ★★★★★ ④ 音源ファイル選択 (オプション) ★★★★★
        audio_frame = ttk.LabelFrame(left_frame, text="④ 音源ファイル (オプション)", padding="10"); audio_frame.pack(fill="x", pady=(0,15))
        self.audio_path_label = ttk.Label(audio_frame, text="音楽ファイルが選択されていません", wraplength=230); self.audio_path_label.pack(fill="x", pady=(0, 10))
        ttk.Button(audio_frame, text="🎵 音楽ファイルを選択...", command=self.select_audio_file).pack(fill="x")
        
        # ③ ショー実行
        action_frame = ttk.LabelFrame(left_frame, text="③ ショー実行", padding="10"); action_frame.pack(fill="x", pady=(0,15))
        self.connect_btn = ttk.Button(action_frame, text="📡 ドローンに接続", command=self.connect_drones, state="disabled"); self.connect_btn.pack(fill="x", pady=(0, 5))
        self.start_btn = ttk.Button(action_frame, text="▶️ ショーを開始", command=self.start_show, state="disabled", style="Accent.TButton"); self.start_btn.pack(fill="x", pady=(5, 5))
        self.stop_btn = ttk.Button(action_frame, text="⏹️ 緊急停止", command=self.emergency_stop, state="disabled", style="Stop.TButton"); self.stop_btn.pack(fill="x", pady=(5, 0))
        
        # 右カラム
        status_bar = ttk.Frame(main_frame, padding=(5,5)); status_bar.grid(row=0, column=1, sticky="ew", pady=(0,5))
        ttk.Label(status_bar, text="ステータス:", style="Header.TLabel").pack(side="left"); ttk.Label(status_bar, textvariable=self.show_status).pack(side="left", padx=5)
        right_frame = ttk.Frame(main_frame); right_frame.grid(row=1, column=1, sticky="nsew"); right_frame.grid_rowconfigure(0, weight=1); right_frame.grid_columnconfigure(0, weight=1)
        log_pane = ttk.PanedWindow(right_frame, orient="horizontal"); log_pane.pack(fill="both", expand=True)
        timeline_frame = ttk.Frame(log_pane); log_pane.add(timeline_frame, weight=1); ttk.Label(timeline_frame, text="タイムライン", style="Header.TLabel").pack(anchor="w", padx=5)
        self.schedule_text = scrolledtext.ScrolledText(timeline_frame, state="disabled", wrap="none", height=10, font=self.font_monospace); self.schedule_text.pack(expand=True, fill="both", padx=5, pady=(0,5))
        log_frame = ttk.Frame(log_pane); log_pane.add(log_frame, weight=1); ttk.Label(log_frame, text="通信ログ", style="Header.TLabel").pack(anchor="w", padx=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, state="disabled", wrap="none", height=10, font=self.font_monospace); self.log_text.pack(expand=True, fill="both", padx=5, pady=(0,5))
        
        # 色設定
        self.log_text.tag_config("INFO", foreground="black"); self.log_text.tag_config("SUCCESS", foreground="#28a745"); self.log_text.tag_config("WARNING", foreground="#ffc107"); self.log_text.tag_config("ERROR", foreground="#dc3545")
        self.schedule_text.tag_config("TAKEOFF", foreground="#28a745", font=(self.font_monospace[0], self.font_monospace[1], 'bold')); self.schedule_text.tag_config("INFO", foreground="black"); self.schedule_text.tag_config("WAIT", foreground="blue"); self.schedule_text.tag_config("WARNING", foreground="#dc3545"); self.schedule_text.tag_config("HEADER", foreground="#0078D7", font=self.font_header); self.schedule_text.tag_config("HIGHLIGHT", background="#d0e9f8")
        # ★★★ 修正点: LAND タグの色設定を追加 ★★★
        self.schedule_text.tag_config("LAND", foreground="#d13438", font=(self.font_monospace[0], self.font_monospace[1], 'bold')) # 緊急停止ボタンに似た色

    def add_drone_entry(self, name=None, ip=''):
        drone_count = len(self.drone_entry_widgets)
        if name is None: name = f'Tello_{chr(65 + drone_count)}'
        widget_dict = {}; row_frame = ttk.Frame(self.ip_entry_frame); row_frame.pack(fill="x", pady=2)
        label = ttk.Label(row_frame, text=f"{name}:"); label.pack(side="left", padx=(0,5))
        entry = ttk.Entry(row_frame); entry.pack(side="left", expand=True, fill="x"); entry.insert(0, ip)
        widget_dict.update({'name': name, 'frame': row_frame, 'ip_widget': entry}); self.drone_entry_widgets.append(widget_dict)
    def remove_drone_entry(self):
        if not self.drone_entry_widgets: return
        widgets_to_remove = self.drone_entry_widgets.pop(); widgets_to_remove['frame'].destroy()
    def load_config(self):
        try:
            with open("tello_config.json", 'r') as f: config_data = json.load(f)
            while self.drone_entry_widgets: self.remove_drone_entry()
            for name, ip in config_data.items(): self.add_drone_entry(name=name, ip=ip)
            self.log({"level": "INFO", "message": f"tello_config.json から設定を読み込みました。"})
        except FileNotFoundError:
            self.log({"level": "WARNING", "message": "設定ファイルが見つかりません。ドローンを１台以上IPアドレスを入力し、保存してください。"})
            if not self.drone_entry_widgets: self.add_drone_entry()
        except Exception as e: self.log({"level": "ERROR", "message": f"設定の読み込みエラー: {e}"})
    def save_config(self):
        config_data = {widgets['name']: widgets['ip_widget'].get() for widgets in self.drone_entry_widgets}
        try:
            with open("tello_config.json", 'w') as f: json.dump(config_data, f, indent=4)
            self.log({"level": "INFO", "message": f"tello_config.json に設定を保存しました。"}); messagebox.showinfo("成功", "IPアドレスを保存しました。")
        except Exception as e: messagebox.showerror("エラー", f"設定の保存に失敗しました: {e}")
    def select_file(self):
        path = filedialog.askopenfilename(title="Scratch 3 プロジェクトファイルを選択", filetypes=[("Scratch プロジェクト", "*.sb3")])
        if path:
            self.sb3_path.set(path); self.sb3_path_label.configure(text=path.split('/')[-1])
            self._reset_ui_to_file_selected_state()
            self.log({"level": "INFO", "message": f"選択されたファイル: {path}"})
            
    def select_audio_file(self):
        path = filedialog.askopenfilename(title="音楽ファイルを選択", filetypes=[("音声ファイル", "*.mp3 *.wav *.ogg")])
        if path:
            self.audio_path.set(path)
            self.audio_path_label.configure(text=path.split('/')[-1])
            self.log({"level": "INFO", "message": f"選択された音楽ファイル: {path}"})

    def parse_scratch_project(self):
        path = self.sb3_path.get()
        if not path: return
        self.log_text.config(state="normal"); self.log_text.delete(1.0, tk.END); self.log_text.config(state="disabled")
        self.log({"level": "INFO", "message": "Scratchファイルの解析を開始します..."})
        parser = ScratchProjectParser(path, self.log_queue); self.schedule, self.total_time = parser.parse_to_schedule()
        self.schedule_text.config(state="normal"); self.schedule_text.delete(1.0, tk.END)
        self.time_to_line_map = {}
        if self.schedule or parser.has_any_valid_action:
            self.schedule_text.insert(tk.END, f"--- 生成されたタイムライン (予想総時間: {self.total_time:.2f}秒) ---\n\n", "HEADER")
            current_line = 3
            grouped_events = {t: [e for e in self.schedule if e['time'] == t] for t in sorted(list(set(e['time'] for e in self.schedule)))}
            for time, events in grouped_events.items():
                start_line = current_line
                for event in events:
                    evt_type = event.get('type'); log_msg = ""
                    if evt_type == 'TAKEOFF': log_msg = f"{time: >6.2f}s | {event.get('target', 'N/A'): <8} | {event.get('text', '')}\n"
                    elif evt_type == 'COMMAND': log_msg = f"{time: >6.2f}s | {event.get('target', 'N/A'): <8} | 実行: {event.get('command', '')}\n"
                    elif evt_type == 'WAIT': log_msg = f"{time: >6.2f}s | {event.get('target', 'N/A'): <8} | 待機: {event.get('text', '')}\n"
                    elif evt_type == 'WARNING': log_msg = f"{time: >6.2f}s | {event.get('text', '')}\n"
                    # ★★★ 修正点: LAND イベントの表示ロジックを追加 ★★★
                    elif evt_type == 'LAND': log_msg = f"{time: >6.2f}s | {event.get('target', 'N/A'): <8} | {event.get('text', '')}\n"
                    
                    self.schedule_text.insert(tk.END, log_msg, evt_type or "INFO"); current_line += 1
                self.time_to_line_map[time] = {'start': start_line, 'end': current_line - 1}
            self.log({"level": "SUCCESS", "message": "解析に成功しました。ドローンに接続してください。"}); self.connect_btn['state'] = 'normal'
            self.show_status.set(f"解析完了。ドローンに接続してください。")
        else:
            self.schedule_text.insert(tk.END, "ファイルから有効なスケジュールを生成できませんでした。\n", "ERROR"); self.schedule_text.insert(tk.END, "ヒント: スプライトに「緑の旗が押されたとき」ブロックがありますか？\n", "INFO"); self.show_status.set("解析失敗")
        self.schedule_text.config(state="disabled")

    def connect_drones(self):
        self.connect_btn['state'] = 'disabled'; self.show_status.set("ドローンに接続中...")
        drones_config = [{'name': w['name'], 'pc_ip': w['ip_widget'].get()} for w in self.drone_entry_widgets]
        if not all(c['pc_ip'] for c in drones_config): messagebox.showerror("エラー", "開始前に、すべてのIPアドレスを入力してください。"); self.connect_btn['state'] = 'normal'; return
        show_runner = ShowRunner(drones_config, self.schedule, self.stop_event, self.log_queue, self.total_time)
        threading.Thread(target=show_runner.connect).start()

    def start_show(self):
        self._set_ui_for_show_running(True)
        self.stop_event.clear(); self.show_status.set("ショー実行中...")
        show_runner = ShowRunner(None, self.schedule, self.stop_event, self.log_queue, self.total_time, self.controllers, self.audio_path.get())
        self.show_thread = threading.Thread(target=show_runner.run_show); self.show_thread.start()

    def emergency_stop(self):
        self.log({"level": "ERROR", "message": "\n!!! ユーザーによる緊急停止が要求されました !!!"}); self.stop_event.set();
        self.show_status.set("緊急停止 - 着陸中...")
        self.stop_btn['state'] = 'disabled'

    def _reset_ui_to_parsed_state(self):
        self.controllers = {}
        self.stop_event.clear()
        self.stop_btn['state'] = 'disabled'
        self.start_btn['state'] = 'disabled'
        self.connect_btn['state'] = 'normal'
        self.parse_btn['state'] = 'normal'
        self.connect_btn.config(text="📡 ドローンに接続")
        self.show_status.set("準備完了。ドローンに接続してください。")
        self.update_timeline_highlight(None)

    def _set_ui_for_show_running(self, is_running):
        state = 'disabled' if is_running else 'normal'
        self.start_btn['state'] = state; self.parse_btn['state'] = state; self.connect_btn['state'] = state
        self.stop_btn['state'] = 'normal' if is_running else 'disabled'
        
    def _reset_ui_to_file_selected_state(self):
        self.parse_btn['state'] = 'normal'; self.connect_btn['state'] = 'disabled'; self.start_btn['state'] = 'disabled'; self.stop_btn['state'] = 'disabled'
        self.connect_btn.config(text="📡 ドローンに接続"); self.show_status.set(f"ファイル選択済み。解析してください。")

    def log(self, log_item): self.log_queue.put(log_item)

    def process_log_queue(self):
        try:
            while not self.log_queue.empty():
                log_item = self.log_queue.get_nowait()
                if isinstance(log_item, dict) and 'type' in log_item:
                    msg_type = log_item['type']
                    if msg_type == 'highlight': self.update_timeline_highlight(log_item.get('time')); continue
                    elif msg_type == 'clear_highlight': self.update_timeline_highlight(None); continue
                    elif msg_type == 'connection_success':
                        self.controllers = log_item['controllers']; self.start_btn['state'] = 'normal'
                        self.connect_btn.config(text="✓ 接続済み"); self.show_status.set("接続完了。ショーを開始できます。"); continue
                    elif msg_type == 'connection_fail':
                        self.connect_btn['state'] = 'normal'; self.show_status.set("接続に失敗しました。再試行してください。"); continue
                    elif msg_type == 'show_finished':
                        self._reset_ui_to_parsed_state(); continue
                
                if isinstance(log_item, dict): level, message = log_item.get("level", "INFO"), log_item.get("message", "")
                else: level, message = "INFO", str(log_item)
                
                self.log_text.config(state="normal"); self.log_text.insert(tk.END, message + '\n', level); self.log_text.see(tk.END); self.log_text.config(state="disabled")
        finally: self.master.after(100, self.process_log_queue)

    def update_timeline_highlight(self, current_time):
        self.schedule_text.config(state="normal")
        if self.last_highlighted_lines:
            self.schedule_text.tag_remove("HIGHLIGHT", f"{self.last_highlighted_lines['start']}.0", f"{self.last_highlighted_lines['end']}.end")
            self.last_highlighted_lines = None
        if current_time is not None and current_time in self.time_to_line_map:
            line_info = self.time_to_line_map[current_time]
            self.schedule_text.tag_add("HIGHLIGHT", f"{line_info['start']}.0", f"{line_info['end']}.end")
            self.schedule_text.see(f"{line_info['start']}.0")
            self.last_highlighted_lines = line_info
        self.schedule_text.config(state="disabled")

    def on_closing(self):
        if self.show_thread and self.show_thread.is_alive():
            if messagebox.askyesno("終了確認", "ショーが実行中です。停止して終了しますか？"): self.emergency_stop(); self.master.destroy()
        else: self.master.destroy()

if __name__ == '__main__':
    if sys.platform == 'win32':
        try: import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    root = tk.Tk(); app = TelloApp(root); root.protocol("WM_DELETE_WINDOW", app.on_closing); root.mainloop()