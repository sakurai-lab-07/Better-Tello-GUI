"""
タイムラインビューワーウィンドウ
"""

import tkinter as tk
from tkinter import ttk
import os

from config import (
    COLOR_BACKGROUND,
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_HIGHLIGHT,
    FONT_NORMAL,
    FONT_BOLD_LARGE,
    FONT_HEADER,
)

# 色の定義（タイムライン用）
COLOR_TIMELINE_BG = "#f0f0f0"
COLOR_TRACK_LABEL_BG = "#e0e0e0"
COLOR_TAKEOFF = "#4caf50"  # Green
COLOR_LAND = "#f44336"  # Red
COLOR_COMMAND = "#2196f3"  # Blue
COLOR_WAIT = "#9e9e9e"  # Gray
COLOR_MUSIC = "#9c27b0"  # Purple
COLOR_PLAYHEAD = "#ff9800"  # Orange


class TimelineViewerWindow:
    """タイムラインビューワーウィンドウクラス"""

    def __init__(
        self, parent, music_list, schedule, total_time, interval, music_player=None
    ):
        """
        タイムラインビューワーの初期化

        Args:
            parent: 親ウィンドウ
            music_list: 音楽リスト
            schedule: 実行スケジュール
            total_time: 総実行時間
            interval: 曲間インターバル
            music_player: MusicPlayerインスタンス（長さ取得用）
        """
        self.parent = parent
        self.music_list = music_list
        self.schedule = schedule
        self.total_time = total_time
        self.interval = interval
        self.music_player = music_player

        # ウィンドウの作成
        self.window = tk.Toplevel(parent)
        self.window.title("タイムラインビューワー")
        self.window.geometry("1000x600")
        self.window.minsize(800, 400)
        self.window.configure(bg=COLOR_BACKGROUND)

        # ズーム倍率 (pixels per second)
        self.zoom_level = tk.DoubleVar(value=20.0)
        self.track_height = 60
        self.label_width = 120

        # UI構築
        self._create_widgets()

        # 初期表示
        self.time_label.config(text=f"時間: 0.00s / {self.total_time:.2f}s")

        # データの描画
        self.window.after(100, self.draw_timeline)

    def _create_widgets(self):
        """UI要素を作成"""
        # ツールバー
        toolbar = ttk.Frame(self.window, padding="5")
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="ズーム:").pack(side="left", padx=5)
        zoom_scale = ttk.Scale(
            toolbar,
            from_=5.0,
            to=100.0,
            variable=self.zoom_level,
            orient="horizontal",
            command=lambda _: self.draw_timeline(),
        )
        zoom_scale.pack(side="left", padx=5, fill="x", expand=True)

        ttk.Button(toolbar, text="リセット", command=self._reset_zoom).pack(
            side="left", padx=5
        )

        self.time_label = ttk.Label(
            toolbar, text="時間: 0.00s / 0.00s", font=FONT_NORMAL
        )
        self.time_label.pack(side="left", padx=20)

        ttk.Button(toolbar, text="閉じる", command=self.window.destroy).pack(
            side="right", padx=5
        )

        # メインエリア（スクロールバー付きキャンバス）
        container = ttk.Frame(self.window)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(container, bg=COLOR_TIMELINE_BG, highlightthickness=0)

        self.h_scroll = ttk.Scrollbar(
            container, orient="horizontal", command=self.canvas.xview
        )
        self.v_scroll = ttk.Scrollbar(
            container, orient="vertical", command=self.canvas.yview
        )

        self.canvas.configure(
            xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set
        )

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")

        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # マウスホイールでのスクロール
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)

        self.playhead_line = None

    def set_playhead(self, current_time):
        """再生ヘッドの位置を更新"""
        total = getattr(self, "display_total_time", self.total_time)
        if current_time is None:
            if self.playhead_line:
                self.canvas.delete(self.playhead_line)
                self.playhead_line = None
            self.time_label.config(text=f"時間: 0.00s / {total:.2f}s")
            return

        self.time_label.config(text=f"時間: {current_time:.2f}s / {total:.2f}s")
        zoom = self.zoom_level.get()
        x = self.label_width + current_time * zoom

        if self.playhead_line:
            self.canvas.coords(
                self.playhead_line, x, 0, x, self.canvas.winfo_height() + 1000
            )
        else:
            self.playhead_line = self.canvas.create_line(
                x,
                0,
                x,
                self.canvas.winfo_height() + 1000,
                fill=COLOR_PLAYHEAD,
                width=2,
                tags="playhead",
            )

        # 再生ヘッドが画面外に出たらスクロール
        # (簡易的な実装)
        # self.canvas.xview_moveto(...)

    def _reset_zoom(self):
        self.zoom_level.set(20.0)
        self.draw_timeline()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def draw_timeline(self):
        """タイムラインを描画"""
        self.canvas.delete("all")

        zoom = self.zoom_level.get()

        # トラックの特定
        drones = sorted(
            list(
                set(
                    e["target"]
                    for e in self.schedule
                    if e.get("target")
                    and e["target"] != "システム"
                    and e["target"] != "ALL"
                )
            )
        )
        tracks = drones + ["音楽"]

        # 音楽の総時間を計算
        total_music_time = 0.0
        if self.music_list:
            for i, path in enumerate(self.music_list):
                duration = 0.0
                if self.music_player:
                    duration = self.music_player.get_music_duration(path)
                if duration <= 0:
                    duration = 10.0
                total_music_time += duration
                if i < len(self.music_list) - 1:
                    total_music_time += self.interval

        display_total_time = max(self.total_time, total_music_time)
        self.display_total_time = display_total_time  # 保存しておく

        total_width = max(
            display_total_time * zoom + self.label_width + 100,
            self.window.winfo_width(),
        )
        total_height = len(tracks) * self.track_height + 40  # 40 is for time axis

        self.canvas.configure(scrollregion=(0, 0, total_width, total_height))

        # 時間軸の描画
        for t in range(0, int(display_total_time) + 10, 5):
            x = self.label_width + t * zoom
            self.canvas.create_line(x, 0, x, total_height, fill="#cccccc", dash=(2, 4))
            self.canvas.create_text(x, 10, text=f"{t}s", anchor="n", font=FONT_NORMAL)

        # トラックの描画
        for i, track in enumerate(tracks):
            y_start = 30 + i * self.track_height
            y_end = y_start + self.track_height

            # トラック背景
            self.canvas.create_rectangle(
                0, y_start, total_width, y_end, fill="white", outline="#dddddd"
            )

            # トラックラベル
            self.canvas.create_rectangle(
                0,
                y_start,
                self.label_width,
                y_end,
                fill=COLOR_TRACK_LABEL_BG,
                outline="#dddddd",
            )
            self.canvas.create_text(
                self.label_width / 2,
                y_start + self.track_height / 2,
                text=track,
                font=FONT_BOLD_LARGE,
            )

            if track == "音楽":
                self._draw_music_track(y_start, zoom)
            else:
                self._draw_drone_track(track, y_start, zoom)

    def _draw_drone_track(self, drone_name, y_start, zoom):
        """ドローンのトラックを描画"""
        y_mid = y_start + self.track_height / 2
        h = 30  # ブロックの高さ

        # ALLターゲットのイベントもこのドローンに含める
        drone_events = [
            e
            for e in self.schedule
            if e.get("target") == drone_name
            or e.get("target") == "ALL"
            or (e.get("target") == "システム" and e.get("type") == "TAKEOFF")
        ]

        for e in drone_events:
            t = e["time"]
            duration = e.get("duration", 1.0)
            etype = e.get("type")

            x_start = self.label_width + t * zoom
            x_end = x_start + duration * zoom

            color = COLOR_COMMAND
            if etype == "TAKEOFF":
                color = COLOR_TAKEOFF
            elif etype == "LAND":
                color = COLOR_LAND
            elif etype == "WAIT":
                color = COLOR_WAIT

            rect_id = self.canvas.create_rectangle(
                x_start,
                y_mid - h / 2,
                x_end,
                y_mid + h / 2,
                fill=color,
                outline="white",
                width=1,
            )

            # テキスト（入りきらない場合は省略）
            text = e.get("text", "")
            if (x_end - x_start) > 20:
                self.canvas.create_text(
                    x_start + 5,
                    y_mid,
                    text=text,
                    anchor="w",
                    fill="white",
                    font=(FONT_NORMAL[0], 8),
                    width=(x_end - x_start - 10),
                )

    def _draw_music_track(self, y_start, zoom):
        """音楽のトラックを描画（波形付き）"""
        if not self.music_list:
            return

        y_mid = y_start + self.track_height / 2
        h = 40  # 波形の表示高さ
        current_time = 0.0

        for i, path in enumerate(self.music_list):
            duration = 0.0
            if self.music_player:
                duration = self.music_player.get_music_duration(path)

            if duration <= 0:
                duration = 10.0  # デフォルト10秒（取得できない場合）

            x_start = self.label_width + current_time * zoom
            x_end = x_start + duration * zoom

            # 背景ボックス
            self.canvas.create_rectangle(
                x_start,
                y_mid - 20,
                x_end,
                y_mid + 20,
                fill=COLOR_MUSIC,
                outline="white",
                width=1,
            )

            # 波形の描画
            if self.music_player:
                # 描画幅に応じてポイント数を決定（1ピクセルあたり1ポイント程度）
                draw_width = x_end - x_start
                if draw_width > 10:
                    num_points = int(draw_width)
                    
                    # キャッシュを確認
                    cache_key = (path, num_points)
                    waveform = self.music_player._waveform_cache.get(cache_key)
                    
                    if waveform:
                        # 波形を線で描画
                        for j, val in enumerate(waveform):
                            px = x_start + j
                            amp = val * 18
                            if amp > 0.5:
                                self.canvas.create_line(
                                    px, y_mid - amp, px, y_mid + amp, 
                                    fill="#e1bee7", width=1
                                )
                    else:
                        # 非同期でリクエスト
                        self.canvas.create_text(
                            x_start + draw_width/2, y_mid,
                            text="Loading waveform...", fill="white", font=(FONT_NORMAL[0], 7)
                        )
                        self.music_player.request_waveform(
                            path, num_points, 
                            callback=lambda _: self.window.after(0, self.draw_timeline)
                        )

            filename = os.path.basename(path)
            self.canvas.create_text(
                x_start + 5,
                y_start + 5,
                text=f"{i+1}: {filename}",
                anchor="nw",
                fill="white",
                font=(FONT_NORMAL[0], 8),
            )

            current_time += duration

            # インターバル
            if i < len(self.music_list) - 1 and self.interval > 0:
                x_int_start = x_end
                x_int_end = x_int_start + self.interval * zoom
                self.canvas.create_rectangle(
                    x_int_start,
                    y_mid - 10,
                    x_int_end,
                    y_mid + 10,
                    fill="#e1bee7",
                    outline="white",
                    width=1,
                )
                current_time += self.interval
