"""
音楽管理ウィンドウ
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import hashlib
from pathlib import Path

from config import (
    COLOR_BACKGROUND,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_SUCCESS,
    COLOR_WARNING,
    FONT_NORMAL,
    FONT_BOLD_LARGE,
    FONT_HEADER,
)
from youtube_downloader import YouTubeDownloader

# BPM検出用のオプショナルインポート
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


class MusicManagerWindow:
    """音楽管理ウィンドウクラス"""

    # BPMキャッシュ（クラス変数）
    _bpm_cache: dict = {}

    def __init__(
        self,
        parent,
        music_player,
        music_list,
        on_save_callback,
        youtube_titles=None,
        bpm_data=None,
    ):
        """
        音楽管理ウィンドウの初期化

        Args:
            parent: 親ウィンドウ
            music_player: MusicPlayerインスタンス
            music_list: 現在の音楽リスト
            on_save_callback: 保存時のコールバック関数
            youtube_titles: YouTubeタイトルのキャッシュ（辞書）
            bpm_data: BPM情報の辞書（音楽パス -> BPM）
        """
        self.parent = parent
        self.music_player = music_player
        self.music_list = music_list.copy()  # コピーを作成
        self.original_music_list = music_list.copy()  # 元のリストを保持
        self.on_save_callback = on_save_callback
        self.preview_index = None

        # YouTubeダウンローダーの初期化
        self.youtube_downloader = YouTubeDownloader()

        # インターバル設定（デフォルト0秒）
        self.interval_seconds = tk.DoubleVar(value=music_player.get_interval())

        # プレビュー音量設定（デフォルト50%）
        self.preview_volume = tk.DoubleVar(value=0.5)

        # YouTubeタイトルのキャッシュ（渡されたものがあれば使用）
        self.youtube_titles: dict = youtube_titles.copy() if youtube_titles else {}

        # BPM情報のキャッシュ（渡されたものがあれば使用）
        self.bpm_data: dict = bpm_data.copy() if bpm_data else {}

        # BPM検出中フラグ
        self.bpm_loading: dict = {}

        # ウィンドウの作成
        self.window = tk.Toplevel(parent)
        self.window.title("音楽管理 - メドレー設定")
        self.window.geometry("700x750")
        self.window.minsize(600, 650)
        self.window.configure(bg=COLOR_BACKGROUND)

        # モーダルウィンドウとして設定
        self.window.transient(parent)
        self.window.grab_set()

        # スタイル設定
        self._configure_styles()

        # UI構築
        self._create_widgets()

        # 既存の音楽リストを表示
        self._refresh_list()

        # ウィンドウを中央に配置
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (self.window.winfo_width() // 2)
        y = (self.window.winfo_screenheight() // 2) - (self.window.winfo_height() // 2)
        self.window.geometry(f"+{x}+{y}")

        # 閉じるボタンの処理
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self):
        """スタイルを設定"""
        s = ttk.Style()
        s.configure("MusicManager.TFrame", background=COLOR_BACKGROUND)
        s.configure(
            "MusicManager.TLabel",
            background=COLOR_BACKGROUND,
            foreground="black",
            font=FONT_NORMAL,
        )
        s.configure("MusicHeader.TLabel", font=FONT_HEADER, foreground=COLOR_ACCENT)

    def _create_widgets(self):
        """UI要素を作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.window, padding="15", style="MusicManager.TFrame")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        # ヘッダー
        header_frame = ttk.Frame(main_frame, style="MusicManager.TFrame")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(
            header_frame,
            text="🎵 音楽メドレー設定",
            style="MusicHeader.TLabel",
        ).pack(side="left")

        ttk.Label(
            header_frame,
            text="複数の音楽ファイルを順番に再生します",
            style="MusicManager.TLabel",
            foreground="#666",
        ).pack(side="left", padx=(10, 0))

        # 音楽リストフレーム
        list_frame = ttk.LabelFrame(
            main_frame, text="音楽リスト（再生順）", padding="10"
        )
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        # リストボックスとスクロールバー
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.listbox = tk.Listbox(
            list_frame,
            font=FONT_NORMAL,
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            height=10,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=self.listbox.yview)

        # リストボックスのダブルクリックでプレビュー
        self.listbox.bind("<Double-Button-1>", lambda e: self._preview_selected())

        # ボタンフレーム（リストの横）
        btn_frame = ttk.Frame(list_frame, style="MusicManager.TFrame")
        btn_frame.grid(row=0, column=2, sticky="ns", padx=(10, 0))

        ttk.Button(btn_frame, text="➕ 追加", command=self._add_music, width=12).pack(
            pady=2
        )
        ttk.Button(
            btn_frame, text="📺 YouTube", command=self._add_from_youtube, width=12
        ).pack(pady=2)
        ttk.Button(btn_frame, text="🗑️ 削除", command=self._remove_music, width=12).pack(
            pady=2
        )
        ttk.Button(btn_frame, text="⬆️ 上へ", command=self._move_up, width=12).pack(
            pady=2
        )
        ttk.Button(btn_frame, text="⬇️ 下へ", command=self._move_down, width=12).pack(
            pady=2
        )
        ttk.Button(
            btn_frame, text="🔊 プレビュー", command=self._preview_selected, width=12
        ).pack(pady=2)
        ttk.Button(btn_frame, text="⏹️ 停止", command=self._stop_preview, width=12).pack(
            pady=2
        )

        # 音量スライダー
        ttk.Label(btn_frame, text="音量:", style="MusicManager.TLabel").pack(
            pady=(10, 0)
        )
        volume_scale = ttk.Scale(
            btn_frame,
            from_=0.0,
            to=1.0,
            orient="horizontal",
            variable=self.preview_volume,
            command=self._on_volume_change,
            length=80,
        )
        volume_scale.pack(pady=2)
        self.volume_label = ttk.Label(
            btn_frame, text="50%", style="MusicManager.TLabel", font=("Arial", 8)
        )
        self.volume_label.pack()

        # インターバル設定フレーム
        interval_frame = ttk.LabelFrame(
            main_frame, text="⏱️ 曲間インターバル設定", padding="10"
        )
        interval_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        interval_inner = ttk.Frame(interval_frame, style="MusicManager.TFrame")
        interval_inner.pack(fill="x")

        ttk.Label(
            interval_inner,
            text="曲と曲の間の待機時間:",
            style="MusicManager.TLabel",
        ).pack(side="left")

        # スピンボックスでインターバルを設定
        interval_spinbox = ttk.Spinbox(
            interval_inner,
            from_=0.0,
            to=10.0,
            increment=0.5,
            textvariable=self.interval_seconds,
            width=10,
            font=FONT_NORMAL,
        )
        interval_spinbox.pack(side="left", padx=(10, 5))

        ttk.Label(
            interval_inner,
            text="秒",
            style="MusicManager.TLabel",
        ).pack(side="left")

        ttk.Label(
            interval_frame,
            text="※ 0秒の場合は連続再生、1秒以上で次の曲までの待機時間を設定できます",
            style="MusicManager.TLabel",
            foreground="#666",
            font=("Arial", 8),
        ).pack(anchor="w", pady=(5, 0))

        # 情報表示フレーム
        info_frame = ttk.Frame(main_frame, style="MusicManager.TFrame")
        info_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        self.info_label = ttk.Label(
            info_frame,
            text="音楽ファイルを追加してください",
            style="MusicManager.TLabel",
            foreground="#666",
        )
        self.info_label.pack(anchor="w")

        # 下部ボタンフレーム
        bottom_frame = ttk.Frame(main_frame, style="MusicManager.TFrame")
        bottom_frame.grid(row=4, column=0, sticky="ew")

        ttk.Button(
            bottom_frame,
            text="✅ 保存して閉じる",
            command=self._save_and_close,
            style="Accent.TButton",
        ).pack(side="right", padx=(5, 0))

        ttk.Button(bottom_frame, text="❌ キャンセル", command=self._on_close).pack(
            side="right"
        )

        ttk.Button(bottom_frame, text="🗑️ すべてクリア", command=self._clear_all).pack(
            side="left"
        )

    def _refresh_list(self):
        """リストボックスを更新"""
        self.listbox.delete(0, tk.END)

        for i, music_path in enumerate(self.music_list, 1):
            # BPM情報を取得
            bpm_str = ""
            if music_path in self.bpm_data:
                bpm = self.bpm_data[music_path]
                bpm_str = f" [{bpm} BPM]"
            elif self.bpm_loading.get(music_path, False):
                bpm_str = " [検出中...]"

            # YouTube URLの場合は特別な表示
            if music_path.startswith("http") and (
                "youtube" in music_path or "youtu.be" in music_path
            ):
                # キャッシュされたタイトルを使用、なければURL
                title = self.youtube_titles.get(music_path, None)
                if title:
                    display_name = f"🎬 {title[:35]}" + (
                        "..." if len(title) > 35 else ""
                    )
                else:
                    display_name = f"🎬 YouTube: {music_path[:35]}..."
            else:
                display_name = os.path.basename(music_path)
                if len(display_name) > 40:
                    display_name = display_name[:37] + "..."

            self.listbox.insert(tk.END, f"{i}. {display_name}{bpm_str}")

        # 情報を更新
        if self.music_list:
            self.info_label.config(
                text=f"合計 {len(self.music_list)} 曲が設定されています",
                foreground=COLOR_SUCCESS,
            )
        else:
            self.info_label.config(
                text="音楽ファイルを追加してください", foreground="#666"
            )

        # BPM検出を開始
        self._detect_all_bpm_async()

    def _add_music(self):
        """音楽ファイルを追加"""
        paths = filedialog.askopenfilenames(
            title="音楽ファイルを選択（複数選択可）",
            filetypes=[
                ("音楽ファイル", "*.mp3;*.wav;*.ogg;*.flac"),
                ("MP3ファイル", "*.mp3"),
                ("WAVファイル", "*.wav"),
                ("OGGファイル", "*.ogg"),
                ("FLACファイル", "*.flac"),
                ("すべてのファイル", "*.*"),
            ],
        )

        if paths:
            for path in paths:
                self.music_list.append(path)
                # BPM検出を非同期で開始
                self._detect_bpm_async(path)

            self._refresh_list()

            # 追加した最初のファイルを選択
            if len(self.music_list) > 0:
                self.listbox.selection_set(len(self.music_list) - len(paths))

    def _add_from_youtube(self):
        """YouTube URLから音源を追加"""
        if not self.youtube_downloader.is_available():
            messagebox.showerror(
                "エラー",
                "yt-dlpがインストールされていません。\n\n"
                "以下のコマンドでインストールしてください:\n"
                "pip install yt-dlp",
                parent=self.window,
            )
            return

        # URL入力ダイアログを作成
        dialog = tk.Toplevel(self.window)
        dialog.title("YouTube音源設定")
        dialog.geometry("500x250")
        dialog.transient(self.window)
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
            font=FONT_NORMAL,
        ).pack(anchor="w", pady=(0, 5))

        ttk.Label(
            content_frame,
            text="※再生時に音声データを一時ファイルとしてキャッシュします",
            font=("Arial", 8),
            foreground="gray",
        ).pack(anchor="w", pady=(0, 10))

        url_entry = ttk.Entry(content_frame, font=FONT_NORMAL)
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

        ttk.Button(button_frame, text="追加", command=on_add).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )

        ttk.Button(button_frame, text="キャンセル", command=on_cancel).pack(
            side="left", fill="x", expand=True
        )

        # Enterキーで追加
        url_entry.bind("<Return>", lambda e: on_add())

        dialog.wait_window()

        # URLが追加された場合、リストに追加
        if result["youtube_url"]:
            self.music_list.append(result["youtube_url"])
            # タイトルをキャッシュに保存
            if result.get("title"):
                self.youtube_titles[result["youtube_url"]] = result["title"]
            self._refresh_list()

            # 追加したファイルを選択
            if len(self.music_list) > 0:
                self.listbox.selection_set(len(self.music_list) - 1)

    def _remove_music(self):
        """選択中の音楽を削除"""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "削除する音楽を選択してください")
            return

        index = selection[0]
        del self.music_list[index]
        self._refresh_list()

        # 選択を維持
        if self.music_list:
            new_index = min(index, len(self.music_list) - 1)
            self.listbox.selection_set(new_index)

    def _move_up(self):
        """選択中の音楽を上に移動"""
        selection = self.listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if index > 0:
            self.music_list[index], self.music_list[index - 1] = (
                self.music_list[index - 1],
                self.music_list[index],
            )
            self._refresh_list()
            self.listbox.selection_set(index - 1)

    def _move_down(self):
        """選択中の音楽を下に移動"""
        selection = self.listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if index < len(self.music_list) - 1:
            self.music_list[index], self.music_list[index + 1] = (
                self.music_list[index + 1],
                self.music_list[index],
            )
            self._refresh_list()
            self.listbox.selection_set(index + 1)

    def _on_volume_change(self, value):
        """音量スライダーの変更時"""
        volume = float(value)
        self.music_player.set_volume(volume)
        self.volume_label.config(text=f"{int(volume * 100)}%")

    def _preview_selected(self):
        """選択中の音楽をプレビュー"""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "プレビューする音楽を選択してください")
            return

        index = selection[0]
        self.preview_index = index

        # プレビュー再生（選択した曲のみ）
        self.music_player.stop()

        # 一時的に音楽リストをクリアして単一ファイルとして再生
        self.music_player.set_music_list([])  # メドレーリストをクリア
        self.music_player.set_music(self.music_list[index])  # 選択した曲を設定

        # 音量を設定してから再生
        self.music_player.set_volume(self.preview_volume.get())
        self.music_player.play(self.music_list[index], delay_seconds=0)

        # ステータス更新
        music_path = self.music_list[index]
        if music_path.startswith("http") and (
            "youtube" in music_path or "youtu.be" in music_path
        ):
            # YouTubeの場合はタイトルを表示
            filename = self.youtube_titles.get(music_path, "YouTube")
        else:
            filename = os.path.basename(music_path)
        self.info_label.config(
            text=f"🔊 プレビュー中: {filename}", foreground=COLOR_ACCENT
        )

    def _stop_preview(self):
        """プレビューを停止"""
        self.music_player.stop()
        self.preview_index = None

        # 元の音楽リストを復元
        self.music_player.set_music_list(self.original_music_list)

        # ステータス更新
        if self.music_list:
            self.info_label.config(
                text=f"合計 {len(self.music_list)} 曲が設定されています",
                foreground=COLOR_SUCCESS,
            )
        else:
            self.info_label.config(
                text="音楽ファイルを追加してください", foreground="#666"
            )

    def _clear_all(self):
        """すべての音楽をクリア"""
        if not self.music_list:
            return

        if messagebox.askyesno(
            "確認", "すべての音楽をクリアしますか？\nこの操作は取り消せません。"
        ):
            self.music_list.clear()
            self._refresh_list()
            self._stop_preview()

    def _save_and_close(self):
        """保存して閉じる"""
        # プレビューを停止
        self._stop_preview()

        # インターバル設定を保存
        interval = self.interval_seconds.get()
        self.music_player.set_interval(interval)

        # コールバックを呼び出し（音楽リスト、インターバル、YouTubeタイトル、BPM情報を渡す）
        self.on_save_callback(
            self.music_list, interval, self.youtube_titles, self.bpm_data
        )

        # ウィンドウを閉じる
        self.window.destroy()

    def _on_close(self):
        """ウィンドウを閉じる"""
        # プレビューを停止
        self._stop_preview()

        # 変更がある場合は確認
        if messagebox.askyesno(
            "確認", "変更を保存せずに閉じますか？\n変更は破棄されます。"
        ):
            self.window.destroy()

    # ==================== BPM検出関連 ====================

    def _detect_all_bpm_async(self):
        """すべての音楽ファイルのBPMを非同期で検出"""
        if not NUMPY_AVAILABLE or not PYDUB_AVAILABLE:
            return

        for music_path in self.music_list:
            if music_path not in self.bpm_data and not self.bpm_loading.get(
                music_path, False
            ):
                self._detect_bpm_async(music_path)

    def _detect_bpm_async(self, music_path: str):
        """BPMを非同期で検出"""
        if not NUMPY_AVAILABLE or not PYDUB_AVAILABLE:
            return

        # 既にBPMがある場合はスキップ
        if music_path in self.bpm_data:
            return

        # 既に検出中の場合はスキップ
        if self.bpm_loading.get(music_path, False):
            return

        # キャッシュを確認
        cache_key = self._get_bpm_cache_key(music_path)
        if cache_key in MusicManagerWindow._bpm_cache:
            self.bpm_data[music_path] = MusicManagerWindow._bpm_cache[cache_key]
            self._refresh_list()
            return

        self.bpm_loading[music_path] = True

        def detect():
            try:
                bpm = self._detect_bpm(music_path)
                if bpm:
                    self.bpm_data[music_path] = bpm
                    MusicManagerWindow._bpm_cache[cache_key] = bpm
            except Exception as e:
                print(f"BPM検出エラー: {music_path}: {e}")
            finally:
                self.bpm_loading[music_path] = False
                # UIを更新（メインスレッドで実行）
                try:
                    self.window.after(0, self._refresh_list)
                except:
                    pass

        thread = threading.Thread(target=detect, daemon=True)
        thread.start()

    def _get_bpm_cache_key(self, music_path: str) -> str:
        """音楽ファイルのBPMキャッシュキーを生成"""
        # YouTube URLの場合
        if music_path.startswith(("http://", "https://")):
            return hashlib.md5(music_path.encode()).hexdigest()

        # ローカルファイルの場合
        actual_path = self._resolve_music_path(music_path)
        if not actual_path:
            return hashlib.md5(music_path.encode()).hexdigest()

        try:
            mtime = os.path.getmtime(actual_path)
            key_str = f"{actual_path}:{mtime}"
            return hashlib.md5(key_str.encode()).hexdigest()
        except:
            return hashlib.md5(actual_path.encode()).hexdigest()

    def _resolve_music_path(self, music_path: str) -> str:
        """音楽パスを実際のファイルパスに解決"""
        if not music_path:
            return None

        # YouTube URLの場合はキャッシュファイルを探す
        if music_path.startswith(("http://", "https://")):
            if hasattr(self.music_player, "temp_dir"):
                url_hash = hashlib.md5(music_path.encode()).hexdigest()
                cache_file = Path(self.music_player.temp_dir) / f"{url_hash}.mp3"
                if cache_file.exists():
                    return str(cache_file)
            return None

        # 通常のファイルパス
        if os.path.exists(music_path):
            return music_path

        return None

    def _detect_bpm(self, music_path: str) -> int:
        """
        音楽ファイルのBPMを検出

        Args:
            music_path: 音楽ファイルのパス

        Returns:
            BPM（整数）、検出できない場合はNone
        """
        actual_path = self._resolve_music_path(music_path)
        if not actual_path:
            return None

        try:
            # 音声ファイルを読み込み
            audio = AudioSegment.from_file(actual_path)

            # モノラルに変換、サンプルレートを下げる（処理高速化）
            audio = audio.set_channels(1)
            audio = audio.set_frame_rate(22050)

            # numpy配列に変換
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            samples = samples / np.max(np.abs(samples))  # 正規化

            # BPMを検出
            bpm = self._estimate_bpm(samples, audio.frame_rate)

            return bpm

        except Exception as e:
            print(f"BPM検出エラー: {e}")
            return None

    def _estimate_bpm(self, samples: np.ndarray, sample_rate: int) -> int:
        """
        サンプルデータからBPMを推定

        Args:
            samples: 音声サンプルデータ
            sample_rate: サンプルレート

        Returns:
            推定BPM（整数）
        """
        # 分析用に最初の30秒を使用（計算量削減）
        max_samples = sample_rate * 30
        if len(samples) > max_samples:
            samples = samples[:max_samples]

        # オンセット検出（音の立ち上がりを検出）
        # ハイパスフィルタで高周波成分を抽出
        hop_length = 512

        # エネルギーの計算
        energy = []
        for i in range(0, len(samples) - hop_length, hop_length):
            frame = samples[i : i + hop_length]
            energy.append(np.sum(frame**2))

        energy = np.array(energy)

        # エネルギーの差分（オンセット強度）
        onset_strength = np.diff(energy)
        onset_strength = np.maximum(onset_strength, 0)  # 正の変化のみ

        if len(onset_strength) < 10:
            return None

        # 自己相関を計算してBPMを推定
        # BPM範囲: 60-200
        min_bpm, max_bpm = 60, 200

        # サンプル間隔からBPMへの変換係数
        samples_per_beat_min = (60.0 / max_bpm) * (sample_rate / hop_length)
        samples_per_beat_max = (60.0 / min_bpm) * (sample_rate / hop_length)

        lag_min = int(samples_per_beat_min)
        lag_max = int(samples_per_beat_max)

        # 自己相関を計算
        autocorr = np.correlate(onset_strength, onset_strength, mode="full")
        autocorr = autocorr[len(autocorr) // 2 :]  # 正のラグのみ

        # 有効範囲のラグを探索
        lag_max = min(lag_max, len(autocorr) - 1)
        if lag_min >= lag_max:
            return None

        # ピークを検出
        autocorr_range = autocorr[lag_min:lag_max]
        if len(autocorr_range) == 0:
            return None

        best_lag = lag_min + np.argmax(autocorr_range)

        # ラグからBPMを計算
        bpm = 60.0 * (sample_rate / hop_length) / best_lag

        # 有効なBPM範囲にクランプ
        bpm = max(min_bpm, min(max_bpm, bpm))

        return int(round(bpm))
