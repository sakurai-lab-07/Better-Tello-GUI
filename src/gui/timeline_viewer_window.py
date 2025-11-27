"""
タイムラインビューアーウィンドウ

動画編集ソフトのようなタイムライン表示で、
音源とドローンの動きを視覚的に表示します。
"""

import tkinter as tk
from tkinter import ttk, Canvas
from typing import List, Dict, Optional, Tuple
import math
import threading
import os
import hashlib
import tempfile
from pathlib import Path

# 波形表示用のオプショナルインポート
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from pydub import AudioSegment

    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

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

    # 波形キャッシュ（クラス変数）
    _waveform_cache: Dict[str, Tuple[List[float], float]] = {}
    _cache_dir = Path(tempfile.gettempdir()) / "tello_waveform_cache"

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
        self.track_height = 60  # トラックの高さ（波形表示のため増加）
        self.header_width = 150  # ヘッダー部分の幅
        self.timeline_padding = 20  # タイムラインの余白

        # 波形データのキャッシュ（インスタンス変数）
        self.waveform_data: Dict[str, Tuple[List[float], float]] = {}
        self.waveform_loading: Dict[str, bool] = {}

        # 音楽ファイルの長さキャッシュ
        self.music_durations: Dict[str, float] = {}

        # YouTubeタイトルのキャッシュ
        self.youtube_titles: Dict[str, str] = {}

        # 再描画デバウンス用
        self._redraw_scheduled = False
        self._redraw_delay = 100  # ms

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

        # 波形データを非同期で読み込み
        self._load_all_waveforms_async()

        # YouTubeタイトルを非同期で取得
        self._load_youtube_titles_async()

        # ウィンドウを中央に配置
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (self.window.winfo_width() // 2)
        y = (self.window.winfo_screenheight() // 2) - (self.window.winfo_height() // 2)
        self.window.geometry(f"+{x}+{y}")

    def _schedule_redraw(self):
        """再描画をスケジュール（デバウンス）"""
        if not self._redraw_scheduled:
            self._redraw_scheduled = True
            self.window.after(self._redraw_delay, self._do_redraw)

    def _do_redraw(self):
        """実際の再描画を実行"""
        self._redraw_scheduled = False
        self._draw_timeline()

    def _organize_by_drone(self) -> Dict[str, List[Dict]]:
        """スケジュールをドローンごとに整理（ALLとTAKEOFFは除外）"""
        drone_schedules = {}

        if not self.schedule:
            return drone_schedules

        for event in self.schedule:
            target = event.get("target", "Unknown")
            event_type = event.get("type", "")

            # ALLターゲットとTAKEOFFイベントは離陸トラックで表示するので除外
            if target == "ALL" or event_type == "TAKEOFF":
                continue

            if target not in drone_schedules:
                drone_schedules[target] = []
            drone_schedules[target].append(event)

        return drone_schedules

    def _get_cache_key(self, music_path: str) -> str:
        """音楽ファイルのキャッシュキーを生成"""
        # 実際のファイルパスを取得
        actual_path = self._resolve_music_path(music_path)
        if not actual_path:
            return hashlib.md5(music_path.encode()).hexdigest()

        # ファイルパスと更新日時からハッシュを生成
        try:
            mtime = os.path.getmtime(actual_path)
            key_str = f"{actual_path}:{mtime}"
            return hashlib.md5(key_str.encode()).hexdigest()
        except:
            return hashlib.md5(actual_path.encode()).hexdigest()

    def _is_youtube_url(self, url: str) -> bool:
        """YouTube URLかどうかを判定"""
        if not url:
            return False
        return url.startswith(("http://", "https://")) and (
            "youtube.com" in url or "youtu.be" in url
        )

    def _resolve_music_path(self, music_path: str) -> Optional[str]:
        """
        音楽パスを実際のファイルパスに解決
        YouTube URLの場合はキャッシュファイルのパスを返す

        Args:
            music_path: 音楽ファイルのパスまたはYouTube URL

        Returns:
            実際のファイルパス、存在しない場合はNone
        """
        if not music_path:
            return None

        # YouTube URLの場合
        if self._is_youtube_url(music_path):
            # MusicPlayerのキャッシュディレクトリを使用
            if hasattr(self.music_player, "temp_dir"):
                url_hash = hashlib.md5(music_path.encode()).hexdigest()
                cache_file = self.music_player.temp_dir / f"{url_hash}.mp3"
                if cache_file.exists():
                    return str(cache_file)
            return None

        # 通常のファイルパス
        if os.path.exists(music_path):
            return music_path

        return None

    def _load_all_waveforms_async(self):
        """すべての音楽ファイルの波形を非同期で読み込み"""
        if not NUMPY_AVAILABLE or not PYDUB_AVAILABLE:
            return

        for music_path in self.music_list:
            # 実際のファイルパスを解決
            actual_path = self._resolve_music_path(music_path)
            if actual_path:
                cache_key = self._get_cache_key(music_path)

                # 既にキャッシュにある場合はスキップ
                if cache_key in TimelineViewerWindow._waveform_cache:
                    self.waveform_data[music_path] = (
                        TimelineViewerWindow._waveform_cache[cache_key]
                    )
                    continue

                # 読み込み中フラグ
                if music_path not in self.waveform_loading:
                    self.waveform_loading[music_path] = True
                    thread = threading.Thread(
                        target=self._load_waveform_data,
                        args=(music_path, actual_path),
                        daemon=True,
                    )
                    thread.start()

    def _load_youtube_titles_async(self):
        """YouTubeタイトルを非同期で取得"""
        for music_path in self.music_list:
            if (
                self._is_youtube_url(music_path)
                and music_path not in self.youtube_titles
            ):
                thread = threading.Thread(
                    target=self._load_youtube_title, args=(music_path,), daemon=True
                )
                thread.start()

    def _load_youtube_title(self, url: str):
        """
        YouTubeタイトルを取得

        Args:
            url: YouTube URL
        """
        try:
            import yt_dlp

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get("title", "Unknown")
                self.youtube_titles[url] = title
                # UIを更新（デバウンス付き）
                self.window.after(0, self._schedule_redraw)
        except Exception as e:
            print(f"YouTubeタイトル取得エラー: {url}: {e}")
            self.youtube_titles[url] = "YouTube"

    def _load_waveform_data(self, music_path: str, actual_path: str):
        """
        音楽ファイルから波形データを読み込み（軽量化版）

        Args:
            music_path: 元の音楽パス（YouTube URLまたはファイルパス）
            actual_path: 実際のファイルパス
        """
        try:
            # 音声ファイルを読み込み
            audio = AudioSegment.from_file(actual_path)

            # 音楽の長さ（秒）
            duration = len(audio) / 1000.0
            self.music_durations[music_path] = duration

            # モノラルに変換（ステレオの場合）
            if audio.channels == 2:
                audio = audio.set_channels(1)

            # サンプルレートを下げて軽量化（8000Hzで十分）
            audio = audio.set_frame_rate(8000)

            # 生のサンプルデータを取得
            samples = np.array(audio.get_array_of_samples())

            # 波形データをさらにダウンサンプリング
            # 1秒あたり30ポイント程度に削減（表示用に十分、軽量化）
            target_points = int(duration * 30)
            if len(samples) > target_points:
                # チャンクごとに最大値を取得（エンベロープ抽出）
                chunk_size = max(1, len(samples) // target_points)
                waveform = []
                for i in range(0, len(samples), chunk_size):
                    chunk = samples[i : i + chunk_size]
                    if len(chunk) > 0:
                        # 絶対値の最大値を取得
                        waveform.append(float(np.max(np.abs(chunk))))
            else:
                waveform = [float(abs(s)) for s in samples]

            # 正規化（0.0 ～ 1.0）
            max_val = max(waveform) if waveform else 1
            if max_val > 0:
                waveform = [v / max_val for v in waveform]

            # キャッシュに保存
            cache_key = self._get_cache_key(music_path)
            TimelineViewerWindow._waveform_cache[cache_key] = (waveform, duration)
            self.waveform_data[music_path] = (waveform, duration)

            # UIを更新（メインスレッドでデバウンス付きで実行）
            self.window.after(0, self._schedule_redraw)

        except Exception as e:
            print(f"波形読み込みエラー: {music_path}: {e}")
        finally:
            self.waveform_loading[music_path] = False

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

        # TAKEOFFイベントまたはALLターゲットのイベントがあるか確認
        has_takeoff = (
            any(
                event.get("type") == "TAKEOFF" or event.get("target") == "ALL"
                for event in self.schedule
            )
            if self.schedule
            else False
        )

        # 計算
        timeline_width = int(
            self.total_time * self.pixels_per_second + self.timeline_padding * 2
        )
        num_tracks = len(self.music_list) + len(self.drone_schedules)
        if has_takeoff:
            num_tracks += 1  # TAKEOFFトラック用に1つ追加
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

        # ドローントラックを描画（TAKEOFFを除く）
        current_y = self._draw_drone_tracks(current_y, timeline_width)

        # TAKEOFFトラックを最後に描画
        if has_takeoff:
            self._draw_takeoff_track(current_y, timeline_width)

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

            # ヘッダー - YouTubeの場合はタイトルを表示
            if self._is_youtube_url(music_path):
                title = self.youtube_titles.get(music_path, "YouTube")
                filename = f"🎬 {title}"
            else:
                filename = music_path.split("/")[-1].split("\\")[-1]

            if len(filename) > 20:
                filename = filename[:17] + "..."

            self.canvas.create_text(
                10,
                current_y + self.track_height // 2,
                text=f"🎵 {i + 1}. {filename}",
                font=FONT_NORMAL,
                fill=COLOR_ACCENT,
                anchor="w",
            )

            # 音楽の長さを取得（キャッシュまたはデフォルト）
            if music_path in self.waveform_data:
                _, music_duration = self.waveform_data[music_path]
            elif music_path in self.music_durations:
                music_duration = self.music_durations[music_path]
            else:
                music_duration = 30.0  # デフォルト

            # 音楽バーの位置
            x_start = (
                self.header_width
                + self.timeline_padding
                + current_time * self.pixels_per_second
            )
            x_end = x_start + music_duration * self.pixels_per_second

            # 音楽バーの背景
            self.canvas.create_rectangle(
                x_start,
                current_y + 5,
                x_end,
                current_y + self.track_height - 5,
                fill=COLOR_ACCENT,
                outline=COLOR_ACCENT,
                width=2,
            )

            # 波形を描画
            self._draw_waveform(music_path, x_start, x_end, current_y)

            # 音楽名を左上に表示
            if len(filename) > 15:
                display_name = filename[:12] + "..."
            else:
                display_name = filename

            self.canvas.create_text(
                x_start + 5,
                current_y + 12,
                text=display_name,
                font=("Arial", 8),
                fill="white",
                anchor="w",
            )

            # 再生時間を右下に表示
            duration_text = (
                f"{int(music_duration // 60)}:{int(music_duration % 60):02d}"
            )
            self.canvas.create_text(
                x_end - 5,
                current_y + self.track_height - 12,
                text=duration_text,
                font=("Arial", 7),
                fill="white",
                anchor="e",
            )

            current_time += music_duration + self.interval
            current_y += self.track_height

        return current_y

    def _draw_waveform(self, music_path: str, x_start: float, x_end: float, y: int):
        """
        波形を描画

        Args:
            music_path: 音楽ファイルのパス
            x_start: 描画開始X座標
            x_end: 描画終了X座標
            y: トラックのY座標
        """
        if music_path not in self.waveform_data:
            # 読み込み中の場合はプレースホルダーを表示
            if self.waveform_loading.get(music_path, False):
                self.canvas.create_text(
                    (x_start + x_end) / 2,
                    y + self.track_height // 2,
                    text="波形読み込み中...",
                    font=("Arial", 8),
                    fill="#aaccdd",
                )
            return

        waveform, _ = self.waveform_data[music_path]
        if not waveform:
            return

        # 描画領域のサイズ
        bar_width = x_end - x_start
        bar_height = self.track_height - 20  # 上下のパディング
        center_y = y + self.track_height // 2

        # 波形ポイント数を画面幅に合わせて調整（3ピクセルごとに1ポイントに削減）
        num_points = min(len(waveform), int(bar_width / 3))
        if num_points <= 0:
            return

        # ダウンサンプリング
        step = max(1, len(waveform) // num_points)

        # 波形を描画（ミラー表示）- リスト内包表記で最適化
        points_upper = []
        points_lower = []

        # バッチ処理でポイントを計算
        waveform_len = len(waveform)
        height_factor = (bar_height / 2) * 0.8

        for i in range(0, waveform_len, step):
            x = x_start + (i / waveform_len) * bar_width
            amplitude = waveform[i] * height_factor

            points_upper.append((x, center_y - amplitude))
            points_lower.append((x, center_y + amplitude))

        # ポイントが十分にある場合は波形を描画
        if len(points_upper) >= 2:
            # 上半分と下半分を結合してポリゴンを作成
            all_points = points_upper + list(reversed(points_lower))
            flat_points = [coord for point in all_points for coord in point]

            # 波形を明るい色で塗りつぶし（smooth=Falseで軽量化）
            self.canvas.create_polygon(
                flat_points,
                fill="#b8d4e8",  # 明るい青白色
                outline="",  # アウトラインを削除して軽量化
                width=0,
                smooth=False,  # スムーズ処理を無効化して軽量化
            )

    def _draw_drone_tracks(self, start_y: int, width: int) -> int:
        """ドローントラックを描画（TAKEOFFイベントを除く）

        Returns:
            次のトラックのY座標
        """
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

            # イベントごとにバーを描画（TAKEOFFは除く）
            for event in events:
                event_type = event.get("type", "INFO")

                # TAKEOFFは別トラックで描画するのでスキップ
                if event_type == "TAKEOFF":
                    continue

                event_time = event.get("time", 0)

                # イベントの推定所要時間（コマンドによって異なる）
                duration = self._estimate_event_duration(event)

                x_start = (
                    self.header_width
                    + self.timeline_padding
                    + event_time * self.pixels_per_second
                )
                x_end = x_start + duration * self.pixels_per_second

                # イベントタイプによって色を変える
                if event_type == "LAND":
                    color = COLOR_ERROR
                elif event_type == "COMMAND":
                    # コマンドの内容で色分け
                    command = event.get("command", "")
                    color = self._get_command_color(command)
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

        return current_y

    def _draw_takeoff_track(self, start_y: int, width: int):
        """TAKEOFFイベントとALLターゲットを専用トラックとして描画（タイムラインの最後）"""
        current_y = start_y

        # TAKEOFFイベントとALLターゲットのイベントを収集
        takeoff_events = (
            [
                event
                for event in self.schedule
                if event.get("type") == "TAKEOFF" or event.get("target") == "ALL"
            ]
            if self.schedule
            else []
        )

        if not takeoff_events:
            return

        # トラック背景
        self.canvas.create_rectangle(
            0,
            current_y,
            self.header_width + width,
            current_y + self.track_height,
            fill="#e8f8e8",  # 薄い緑色の背景
            outline="#ccc",
        )

        # ヘッダー
        self.canvas.create_text(
            self.header_width // 2,
            current_y + self.track_height // 2,
            text="🛫 離陸",
            font=FONT_NORMAL,
            fill=COLOR_SUCCESS,
            anchor="w",
        )

        # TAKEOFFイベントを描画
        for event in takeoff_events:
            event_time = event.get("time", 0)
            duration = self._estimate_event_duration(event)

            x_start = (
                self.header_width
                + self.timeline_padding
                + event_time * self.pixels_per_second
            )
            x_end = x_start + duration * self.pixels_per_second

            # イベントバー
            self.canvas.create_rectangle(
                x_start,
                current_y + 8,
                x_end,
                current_y + self.track_height - 8,
                fill=COLOR_SUCCESS,
                outline=COLOR_SUCCESS,
                width=1,
            )

            # イベント名
            event_text = event.get("text", "離陸")
            if len(event_text) > 20:
                event_text = event_text[:17] + "..."

            if x_end - x_start > 30:
                self.canvas.create_text(
                    (x_start + x_end) // 2,
                    current_y + self.track_height // 2,
                    text=event_text,
                    font=("Arial", 7),
                    fill="white",
                )

    def _get_command_color(self, command: str) -> str:
        """
        コマンドの内容に応じた色を返す

        Args:
            command: ドローンコマンド文字列

        Returns:
            色コード（HEX形式）
        """
        command_lower = command.lower()

        # 左右移動（left/right）- 青系
        if "left" in command_lower or "right" in command_lower:
            return "#3498db"  # 明るい青

        # 上下移動（up/down）- 紫系
        if "up" in command_lower or "down" in command_lower:
            return "#9b59b6"  # 紫

        # 前後移動（forward/back）- オレンジ系
        if "forward" in command_lower or "back" in command_lower:
            return "#e67e22"  # オレンジ

        # 回転（cw/ccw/rotate）- ピンク系
        if "cw" in command_lower or "ccw" in command_lower or "rotate" in command_lower:
            return "#e91e63"  # ピンク

        # フリップ - 水色
        if "flip" in command_lower:
            return "#00bcd4"  # シアン

        # その他のコマンド - グレー
        return "#7f8c8d"

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
