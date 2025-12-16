"""
タイムラインビューアーウィンドウ
動画編集ソフト風のタイムラインUIで音楽とドローンの動きを表示
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
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

# pygame関連
try:
    import pygame.mixer

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class TimelineViewerWindow:
    """タイムラインビューアーウィンドウクラス"""

    def __init__(self, parent, music_list, schedule, total_time, interval_seconds=0.0):
        """
        タイムラインビューアーの初期化

        Args:
            parent: 親ウィンドウ
            music_list: 音楽ファイルのリスト
            schedule: ドローンのスケジュール
            total_time: ショーの総実行時間
            interval_seconds: 曲間インターバル
        """
        self.parent = parent
        self.music_list = music_list
        self.schedule = schedule
        self.total_time = total_time
        self.interval_seconds = interval_seconds

        # ウィンドウの作成
        self.window = tk.Toplevel(parent)
        self.window.title("タイムラインビューアー")
        self.window.geometry("1000x600")
        self.window.minsize(800, 500)
        self.window.configure(bg=COLOR_BACKGROUND)

        # モーダルにしない（並行して操作可能）
        self.window.transient(parent)

        # タイムライン設定
        self.timeline_start_x = 150  # タイムライン開始位置（左マージン）
        self.timeline_width = 800  # タイムライン幅
        self.row_height = 40  # 各行の高さ
        self.header_height = 60  # ヘッダーの高さ
        self.pixels_per_second = 50  # 1秒あたりのピクセル数（初期値）

        # スクロール位置
        self.scroll_x = 0

        # UI構築
        self._create_widgets()
        self._draw_timeline()

        # ウィンドウを中央に配置
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (self.window.winfo_width() // 2)
        y = (self.window.winfo_screenheight() // 2) - (self.window.winfo_height() // 2)
        self.window.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """UI要素を作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill="both", expand=True)

        # ヘッダーフレーム
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(
            header_frame,
            text="🎬 タイムラインビューアー",
            font=FONT_HEADER,
            foreground=COLOR_ACCENT,
        ).pack(side="left")

        ttk.Label(
            header_frame,
            text=f"総時間: {self.total_time:.1f}秒",
            font=FONT_NORMAL,
            foreground="#666",
        ).pack(side="left", padx=(20, 0))

        # ズームコントロール
        zoom_frame = ttk.Frame(header_frame)
        zoom_frame.pack(side="right")

        ttk.Label(zoom_frame, text="ズーム:", font=FONT_NORMAL).pack(side="left")

        ttk.Button(zoom_frame, text="－", command=self._zoom_out, width=3).pack(
            side="left", padx=2
        )

        self.zoom_label = ttk.Label(zoom_frame, text="100%", font=FONT_NORMAL, width=6)
        self.zoom_label.pack(side="left", padx=5)

        ttk.Button(zoom_frame, text="＋", command=self._zoom_in, width=3).pack(
            side="left", padx=2
        )

        # キャンバスフレーム
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill="both", expand=True)

        # 横スクロールバー
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient="horizontal")
        h_scrollbar.pack(side="bottom", fill="x")

        # 縦スクロールバー
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical")
        v_scrollbar.pack(side="right", fill="y")

        # キャンバス
        self.canvas = tk.Canvas(
            canvas_frame,
            bg="white",
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set,
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        h_scrollbar.config(command=self.canvas.xview)
        v_scrollbar.config(command=self.canvas.yview)

        # 凡例フレーム
        legend_frame = ttk.Frame(main_frame)
        legend_frame.pack(fill="x", pady=(10, 0))

        ttk.Label(legend_frame, text="凡例:", font=FONT_BOLD_LARGE).pack(side="left")

        self._create_legend_item(legend_frame, "#90EE90", "音楽トラック")
        self._create_legend_item(legend_frame, "#87CEEB", "ドローン動作")
        self._create_legend_item(legend_frame, "#FFB6C1", "待機時間")
        self._create_legend_item(legend_frame, "#FFE4B5", "インターバル")

    def _create_legend_item(self, parent, color, text):
        """凡例アイテムを作成"""
        item_frame = ttk.Frame(parent)
        item_frame.pack(side="left", padx=(15, 0))

        color_box = tk.Canvas(
            item_frame, width=20, height=15, bg=color, highlightthickness=1
        )
        color_box.pack(side="left")

        ttk.Label(item_frame, text=text, font=FONT_NORMAL).pack(
            side="left", padx=(5, 0)
        )

    def _get_music_duration(self, music_path):
        """
        音楽ファイルの長さを取得

        Args:
            music_path: 音楽ファイルのパス

        Returns:
            float: 音楽の長さ（秒）、取得できない場合はNone
        """
        if not PYGAME_AVAILABLE:
            return None

        try:
            # pygameの初期化が必要
            if not pygame.mixer.get_init():
                pygame.mixer.init()

            sound = pygame.mixer.Sound(music_path)
            duration = sound.get_length()
            return duration
        except Exception as e:
            print(f"音楽ファイルの長さ取得エラー ({os.path.basename(music_path)}): {e}")
            return None

    def _draw_timeline(self):
        """タイムラインを描画"""
        self.canvas.delete("all")

        # 音楽の合計時間を計算（音楽がドローンより長い場合に対応）
        music_total_time = 0
        if self.music_list:
            for i, music_path in enumerate(self.music_list):
                duration = self._get_music_duration(music_path)
                if duration is None:
                    # 取得できない場合は仮の値を使用
                    duration = (
                        self.total_time / len(self.music_list) if self.music_list else 0
                    )
                music_total_time += duration
                # インターバルを追加
                if i < len(self.music_list) - 1:
                    music_total_time += self.interval_seconds

        # タイムラインの表示幅を決定（ドローンと音楽のどちらか長い方）
        display_time = max(self.total_time, music_total_time)

        # キャンバスサイズを計算
        total_width = (
            self.timeline_start_x + int(display_time * self.pixels_per_second) + 100
        )

        # ドローン名を取得
        drone_names = self._get_drone_names()
        num_rows = len(drone_names) + 1  # 音楽トラック + ドローン数

        total_height = self.header_height + (num_rows * self.row_height) + 50

        self.canvas.config(scrollregion=(0, 0, total_width, total_height))

        # 時間軸を描画（表示時間を使用）
        self._draw_time_axis(display_time)

        # 音楽トラックを描画
        current_y = self.header_height
        self._draw_music_track(current_y, display_time)

        # 各ドローンのトラックを描画
        current_y += self.row_height
        for drone_name in drone_names:
            self._draw_drone_track(drone_name, current_y, display_time)
            current_y += self.row_height

    def _get_drone_names(self):
        """スケジュールからドローン名を取得"""
        drone_names = set()
        if self.schedule:
            for event in self.schedule:
                if event.get("type") in ["COMMAND", "WAIT"]:
                    drone_names.add(event.get("target"))
        return sorted(list(drone_names))

    def _draw_time_axis(self, display_time=None):
        """
        時間軸を描画

        Args:
            display_time: 表示する時間の長さ（秒）。Noneの場合はself.total_timeを使用
        """
        if display_time is None:
            display_time = self.total_time

        y = self.header_height - 10

        # 時間軸のライン
        self.canvas.create_line(
            self.timeline_start_x,
            y,
            self.timeline_start_x + int(display_time * self.pixels_per_second),
            y,
            fill="black",
            width=2,
        )

        # ズーム倍率に応じて表示間隔を決定
        # pixels_per_secondが小さい（ズームアウト）ほど、間隔を広げる
        if self.pixels_per_second >= 80:
            interval = 1  # 1秒ごと
        elif self.pixels_per_second >= 40:
            interval = 2  # 2秒ごと
        elif self.pixels_per_second >= 20:
            interval = 5  # 5秒ごと
        else:
            interval = 10  # 10秒ごと

        # 時間マーカー
        for t in range(0, int(display_time) + 1):
            x = self.timeline_start_x + int(t * self.pixels_per_second)

            # 小さな目盛り（1秒ごと）
            if t % interval == 0:
                # 大きな目盛りとラベル
                self.canvas.create_line(x, y - 5, x, y + 5, fill="black", width=2)

                # 時間ラベル
                self.canvas.create_text(
                    x, y - 15, text=f"{t}s", font=("Arial", 9), fill="black"
                )
            else:
                # 小さな目盛り
                self.canvas.create_line(x, y - 3, x, y + 3, fill="gray", width=1)

            # グリッドライン（主要な間隔のみ）
            if t % interval == 0:
                grid_height = (
                    self.header_height
                    + (len(self._get_drone_names()) + 1) * self.row_height
                )
                self.canvas.create_line(
                    x,
                    self.header_height,
                    x,
                    grid_height,
                    fill="#E0E0E0",
                    width=1,
                    dash=(2, 4),
                )

    def _draw_music_track(self, y, display_time=None):
        """
        音楽トラックを描画

        Args:
            y: トラックのY座標
            display_time: 表示する時間の長さ（秒）。Noneの場合はself.total_timeを使用
        """
        if display_time is None:
            display_time = self.total_time

        # トラックラベル
        self.canvas.create_text(
            10,
            y + self.row_height // 2,
            text="🎵 音楽",
            font=FONT_BOLD_LARGE,
            anchor="w",
            fill=COLOR_ACCENT,
        )

        # トラック背景
        self.canvas.create_rectangle(
            self.timeline_start_x,
            y,
            self.timeline_start_x + int(display_time * self.pixels_per_second),
            y + self.row_height,
            fill="#F5F5F5",
            outline="#CCCCCC",
        )

        # 音楽ファイルを配置
        current_time = 0
        for i, music_path in enumerate(self.music_list):
            filename = os.path.basename(music_path)

            # 実際のファイルから長さを取得
            duration = self._get_music_duration(music_path)
            if duration is None:
                # 取得できない場合は仮の長さを使用
                if self.music_list:
                    duration = self.total_time / len(self.music_list)
                else:
                    duration = 0

            x1 = self.timeline_start_x + int(current_time * self.pixels_per_second)
            x2 = self.timeline_start_x + int(
                (current_time + duration) * self.pixels_per_second
            )

            # 音楽ブロック
            self.canvas.create_rectangle(
                x1,
                y + 5,
                x2,
                y + self.row_height - 5,
                fill="#90EE90",
                outline="#228B22",
                width=2,
            )

            # ファイル名（短縮）
            display_name = filename if len(filename) < 20 else filename[:17] + "..."
            self.canvas.create_text(
                x1 + 5,
                y + self.row_height // 2,
                text=display_name,
                font=("Arial", 9),
                anchor="w",
                fill="black",
            )

            current_time += duration

            # インターバル
            if i < len(self.music_list) - 1 and self.interval_seconds > 0:
                interval_x1 = x2
                interval_x2 = interval_x1 + int(
                    self.interval_seconds * self.pixels_per_second
                )

                self.canvas.create_rectangle(
                    interval_x1,
                    y + 5,
                    interval_x2,
                    y + self.row_height - 5,
                    fill="#FFE4B5",
                    outline="#FFA500",
                    width=1,
                    dash=(4, 2),
                )

                self.canvas.create_text(
                    interval_x1 + 3,
                    y + 10,
                    text="待機",
                    font=("Arial", 8),
                    anchor="w",
                    fill="#FF8C00",
                )

                current_time += self.interval_seconds

    def _draw_drone_track(self, drone_name, y, display_time=None):
        """
        ドローンのトラックを描画

        Args:
            drone_name: ドローン名
            y: トラックのY座標
            display_time: 表示する時間の長さ（秒）。Noneの場合はself.total_timeを使用
        """
        if display_time is None:
            display_time = self.total_time

        # トラックラベル
        self.canvas.create_text(
            10,
            y + self.row_height // 2,
            text=f"🚁 {drone_name}",
            font=FONT_NORMAL,
            anchor="w",
            fill="#333",
        )

        # トラック背景
        self.canvas.create_rectangle(
            self.timeline_start_x,
            y,
            self.timeline_start_x + int(display_time * self.pixels_per_second),
            y + self.row_height,
            fill="#FAFAFA",
            outline="#CCCCCC",
        )

        # スケジュールからこのドローンのイベントを抽出
        if not self.schedule:
            return

        for event in self.schedule:
            if event.get("target") != drone_name:
                continue

            start_time = event.get("time", 0)

            if event.get("type") == "COMMAND":
                # コマンド実行ブロック
                command = event.get("command", "")
                duration = 0.5  # コマンドの仮の実行時間

                x1 = self.timeline_start_x + int(start_time * self.pixels_per_second)
                x2 = x1 + int(duration * self.pixels_per_second)

                self.canvas.create_rectangle(
                    x1,
                    y + 8,
                    x2,
                    y + self.row_height - 8,
                    fill="#87CEEB",
                    outline="#4682B4",
                    width=2,
                )

                # コマンド名を短縮表示
                cmd_text = command if len(command) < 10 else command[:7] + "..."
                self.canvas.create_text(
                    x1 + 3,
                    y + self.row_height // 2,
                    text=cmd_text,
                    font=("Arial", 8),
                    anchor="w",
                    fill="black",
                )

            elif event.get("type") == "WAIT":
                # 待機ブロック
                wait_time = event.get("duration", 0)

                x1 = self.timeline_start_x + int(start_time * self.pixels_per_second)
                x2 = x1 + int(wait_time * self.pixels_per_second)

                self.canvas.create_rectangle(
                    x1,
                    y + 8,
                    x2,
                    y + self.row_height - 8,
                    fill="#FFB6C1",
                    outline="#FF69B4",
                    width=1,
                )

                self.canvas.create_text(
                    x1 + 3,
                    y + self.row_height // 2,
                    text=f"待機 {wait_time:.1f}s",
                    font=("Arial", 8),
                    anchor="w",
                    fill="#8B008B",
                )

    def _zoom_in(self):
        """ズームイン"""
        self.pixels_per_second = min(200, self.pixels_per_second * 1.5)
        self._update_zoom_label()
        self._draw_timeline()

    def _zoom_out(self):
        """ズームアウト"""
        self.pixels_per_second = max(10, self.pixels_per_second / 1.5)
        self._update_zoom_label()
        self._draw_timeline()

    def _update_zoom_label(self):
        """ズームラベルを更新"""
        zoom_percent = int((self.pixels_per_second / 50) * 100)
        self.zoom_label.config(text=f"{zoom_percent}%")
