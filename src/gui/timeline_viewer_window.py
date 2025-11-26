"""
タイムラインビューアーウィンドウ

動画編集ソフトのようなタイムライン表示で、
音源とドローンの動きを視覚的に表示します。
"""

import tkinter as tk
from tkinter import ttk, Canvas
from typing import List, Dict, Optional
import math

from config import (
    COLOR_BACKGROUND,
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_HIGHLIGHT,
    COLOR_TEXT,
    FONT_NORMAL,
    FONT_HEADER,
)


class TimelineViewerWindow:
    """タイムラインビューアーウィンドウクラス"""

    def __init__(
        self,
        parent,
        schedule: List[Dict],
        total_time: float,
        music_list: List[str],
        music_player,
    ):
        """
        タイムラインビューアーの初期化

        Args:
            parent: 親ウィンドウ
            schedule: ドローンのスケジュール
            total_time: 総実行時間（秒）
            music_list: 音楽ファイルリスト
            music_player: MusicPlayerインスタンス
        """
        self.parent = parent
        self.schedule = schedule
        self.total_time = total_time
        self.music_list = music_list
        self.music_player = music_player
        self.interval = music_player.get_interval()

        # タイムラインの設定
        self.pixels_per_second = 50  # 1秒あたりのピクセル数
        self.track_height = 40  # トラックの高さ
        self.header_width = 150  # ヘッダー部分の幅
        self.timeline_padding = 20  # タイムラインの余白

        # ドローンごとのスケジュールを抽出
        self.drone_schedules = self._organize_by_drone()

        # ウィンドウの作成
        self.window = tk.Toplevel(parent)
        self.window.title("📊 タイムラインビューアー")
        self.window.geometry("1200x700")
        self.window.minsize(800, 500)
        self.window.configure(bg=COLOR_BACKGROUND)

        # モーダルウィンドウとして設定
        self.window.transient(parent)

        self._create_widgets()
        self._draw_timeline()

        # ウィンドウを中央に配置
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (self.window.winfo_width() // 2)
        y = (self.window.winfo_screenheight() // 2) - (self.window.winfo_height() // 2)
        self.window.geometry(f"+{x}+{y}")

    def _organize_by_drone(self) -> Dict[str, List[Dict]]:
        """スケジュールをドローンごとに整理"""
        drone_schedules = {}

        if not self.schedule:
            return drone_schedules

        for event in self.schedule:
            target = event.get("target", "Unknown")
            if target not in drone_schedules:
                drone_schedules[target] = []
            drone_schedules[target].append(event)

        return drone_schedules

    def _create_widgets(self):
        """UI要素を作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill="both", expand=True)

        # ヘッダー
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(
            header_frame,
            text="📊 タイムラインビューアー",
            font=FONT_HEADER,
            foreground=COLOR_ACCENT,
        ).pack(side="left")

        ttk.Label(
            header_frame,
            text=f"総時間: {self.total_time:.1f}秒 | ドローン数: {len(self.drone_schedules)}",
            font=FONT_NORMAL,
            foreground="#666",
        ).pack(side="left", padx=(20, 0))

        # スクロール可能なキャンバス
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill="both", expand=True)

        # 横スクロールバー
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient="horizontal")
        h_scrollbar.pack(side="bottom", fill="x")

        # 縦スクロールバー
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical")
        v_scrollbar.pack(side="right", fill="y")

        # キャンバス
        self.canvas = Canvas(
            canvas_frame,
            bg="white",
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set,
            highlightthickness=1,
            highlightbackground="#ccc",
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        h_scrollbar.config(command=self.canvas.xview)
        v_scrollbar.config(command=self.canvas.yview)

        # マウスホイールでのスクロールをバインド
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)

        # ズーム制御フレーム
        zoom_frame = ttk.Frame(main_frame)
        zoom_frame.pack(fill="x", pady=(10, 0))

        ttk.Label(zoom_frame, text="ズーム:").pack(side="left", padx=(0, 5))

        ttk.Button(zoom_frame, text="－", width=3, command=self._zoom_out).pack(
            side="left", padx=2
        )
        ttk.Button(zoom_frame, text="＋", width=3, command=self._zoom_in).pack(
            side="left", padx=2
        )
        ttk.Button(zoom_frame, text="リセット", command=self._zoom_reset).pack(
            side="left", padx=(10, 0)
        )

        self.zoom_label = ttk.Label(zoom_frame, text="100%")
        self.zoom_label.pack(side="left", padx=(10, 0))

        # 閉じるボタン
        ttk.Button(zoom_frame, text="閉じる", command=self.window.destroy).pack(
            side="right"
        )

    def _draw_timeline(self):
        """タイムラインを描画"""
        self.canvas.delete("all")

        # 計算
        timeline_width = int(
            self.total_time * self.pixels_per_second + self.timeline_padding * 2
        )
        num_tracks = len(self.music_list) + len(self.drone_schedules)
        timeline_height = (
            num_tracks + 1
        ) * self.track_height + self.timeline_padding * 2

        # キャンバスのスクロール領域を設定
        self.canvas.config(
            scrollregion=(0, 0, self.header_width + timeline_width, timeline_height)
        )

        # 初回描画時は左端にスクロール
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

        current_y = self.timeline_padding

        # タイムスケールを描画
        self._draw_time_scale(current_y, timeline_width)
        current_y += self.track_height

        # 音楽トラックを描画
        if self.music_list:
            current_y = self._draw_music_tracks(current_y, timeline_width)

        # ドローントラックを描画
        self._draw_drone_tracks(current_y, timeline_width)

    def _draw_time_scale(self, y: int, width: int):
        """タイムスケールを描画"""
        # 背景
        self.canvas.create_rectangle(
            0,
            y,
            self.header_width + width,
            y + self.track_height,
            fill="#f8f8f8",
            outline="#ddd",
        )

        # ヘッダーラベル
        self.canvas.create_text(
            self.header_width // 2,
            y + self.track_height // 2,
            text="タイムライン",
            font=FONT_HEADER,
            fill=COLOR_TEXT,
        )

        # 時間目盛り
        interval = 1  # 1秒ごと
        for t in range(0, int(self.total_time) + 1, interval):
            x = self.header_width + self.timeline_padding + t * self.pixels_per_second

            # 目盛り線
            self.canvas.create_line(
                x,
                y + self.track_height - 10,
                x,
                y + self.track_height,
                fill="#999",
                width=1,
            )

            # 時間ラベル（5秒ごと）
            if t % 5 == 0:
                self.canvas.create_text(
                    x,
                    y + self.track_height // 2,
                    text=f"{t}s",
                    font=("Arial", 8),
                    fill="#666",
                )

    def _draw_music_tracks(self, start_y: int, width: int) -> int:
        """音楽トラックを描画"""
        current_y = start_y
        current_time = 0.0

        for i, music_path in enumerate(self.music_list):
            # トラック背景
            self.canvas.create_rectangle(
                0,
                current_y,
                self.header_width + width,
                current_y + self.track_height,
                fill="#e8f4f8",
                outline="#ccc",
            )

            # ヘッダー
            filename = music_path.split("/")[-1].split("\\")[-1]
            if len(filename) > 20:
                filename = filename[:17] + "..."

            self.canvas.create_text(
                self.header_width // 2,
                current_y + self.track_height // 2,
                text=f"🎵 {i + 1}. {filename}",
                font=FONT_NORMAL,
                fill=COLOR_ACCENT,
                anchor="w",
            )

            # 音楽の推定長さ（仮に30秒とする。実際の長さはpygameで取得可能）
            music_duration = 30.0  # TODO: 実際の音楽ファイルから長さを取得

            # 音楽バー
            x_start = (
                self.header_width
                + self.timeline_padding
                + current_time * self.pixels_per_second
            )
            x_end = x_start + music_duration * self.pixels_per_second

            self.canvas.create_rectangle(
                x_start,
                current_y + 5,
                x_end,
                current_y + self.track_height - 5,
                fill=COLOR_ACCENT,
                outline=COLOR_ACCENT,
                width=2,
            )

            # 音楽名を中央に表示
            if len(filename) > 15:
                display_name = filename[:12] + "..."
            else:
                display_name = filename

            self.canvas.create_text(
                (x_start + x_end) // 2,
                current_y + self.track_height // 2,
                text=display_name,
                font=("Arial", 8),
                fill="white",
            )

            current_time += music_duration + self.interval
            current_y += self.track_height

        return current_y

    def _draw_drone_tracks(self, start_y: int, width: int):
        """ドローントラックを描画"""
        current_y = start_y

        for drone_name, events in sorted(self.drone_schedules.items()):
            # トラック背景
            self.canvas.create_rectangle(
                0,
                current_y,
                self.header_width + width,
                current_y + self.track_height,
                fill="#fff",
                outline="#ccc",
            )

            # ヘッダー
            self.canvas.create_text(
                self.header_width // 2,
                current_y + self.track_height // 2,
                text=f"🚁 {drone_name}",
                font=FONT_NORMAL,
                fill=COLOR_TEXT,
                anchor="w",
            )

            # イベントごとにバーを描画
            for event in events:
                event_time = event.get("time", 0)
                event_type = event.get("type", "INFO")

                # イベントの推定所要時間（コマンドによって異なる）
                duration = self._estimate_event_duration(event)

                x_start = (
                    self.header_width
                    + self.timeline_padding
                    + event_time * self.pixels_per_second
                )
                x_end = x_start + duration * self.pixels_per_second

                # イベントタイプによって色を変える
                if event_type == "TAKEOFF":
                    color = COLOR_SUCCESS
                elif event_type == "LAND":
                    color = COLOR_ERROR
                elif event_type == "COMMAND":
                    color = COLOR_WARNING
                else:
                    color = "#ccc"

                # イベントバー
                self.canvas.create_rectangle(
                    x_start,
                    current_y + 8,
                    x_end,
                    current_y + self.track_height - 8,
                    fill=color,
                    outline=color,
                    width=1,
                )

                # イベント名（短縮表示）
                event_text = event.get("text", event.get("command", ""))
                if len(event_text) > 10:
                    event_text = event_text[:8] + "..."

                if x_end - x_start > 30:  # 十分な幅がある場合のみテキスト表示
                    self.canvas.create_text(
                        (x_start + x_end) // 2,
                        current_y + self.track_height // 2,
                        text=event_text,
                        font=("Arial", 7),
                        fill="white",
                    )

            current_y += self.track_height

    def _estimate_event_duration(self, event: Dict) -> float:
        """イベントの推定所要時間を計算（秒）"""
        event_type = event.get("type", "INFO")

        if event_type == "TAKEOFF":
            return 3.0  # 離陸は約3秒
        elif event_type == "LAND":
            return 3.0  # 着陸は約3秒
        elif event_type == "COMMAND":
            command = event.get("command", "")
            # コマンドに応じて時間を推定
            if (
                "forward" in command
                or "back" in command
                or "left" in command
                or "right" in command
            ):
                # 移動コマンドの距離から推定（例: forward 100 → 約2秒）
                try:
                    distance = int(command.split()[-1])
                    return distance / 50.0  # 50cm/秒と仮定
                except:
                    return 1.0
            elif "rotate" in command or "cw" in command or "ccw" in command:
                # 回転コマンド
                try:
                    angle = int(command.split()[-1])
                    return angle / 90.0  # 90度/秒と仮定
                except:
                    return 1.0
            else:
                return 1.0
        elif event_type == "WAIT":
            # 待機時間
            text = event.get("text", "")
            try:
                # "待機: X秒" の形式から抽出
                if "秒" in text:
                    return float(text.split("秒")[0].split()[-1])
            except:
                pass
            return 1.0
        else:
            return 0.5

    def _zoom_in(self):
        """ズームイン"""
        self.pixels_per_second = int(self.pixels_per_second * 1.2)
        self._update_zoom_label()
        self._draw_timeline()

    def _zoom_out(self):
        """ズームアウト"""
        self.pixels_per_second = max(10, int(self.pixels_per_second / 1.2))
        self._update_zoom_label()
        self._draw_timeline()

    def _zoom_reset(self):
        """ズームをリセット"""
        self.pixels_per_second = 50
        self._update_zoom_label()
        self._draw_timeline()

    def _update_zoom_label(self):
        """ズームラベルを更新"""
        zoom_percent = int((self.pixels_per_second / 50) * 100)
        self.zoom_label.config(text=f"{zoom_percent}%")

    def _on_mousewheel(self, event):
        """マウスホイールで縦スクロール"""
        # Windowsの場合: event.delta は 120 or -120
        # 正の値で上スクロール、負の値で下スクロール
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        """Shift+マウスホイールで横スクロール"""
        self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
