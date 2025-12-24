"""
音楽管理ウィンドウ
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
import os

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


class MusicManagerWindow:
    """音楽管理ウィンドウクラス"""

    def __init__(self, parent, music_player, music_list, on_save_callback):
        """
        音楽管理ウィンドウの初期化

        Args:
            parent: 親ウィンドウ
            music_player: MusicPlayerインスタンス
            music_list: 現在の音楽リスト
            on_save_callback: 保存時のコールバック関数
        """
        self.parent = parent
        self.music_player = music_player
        self.music_list = music_list.copy()  # コピーを作成
        self.original_music_list = music_list.copy()  # 元のリストを保持
        self.on_save_callback = on_save_callback
        self.preview_index = None

        # インターバル設定（デフォルト0秒）
        self.interval_seconds = tk.DoubleVar(value=music_player.get_interval())

        # ウィンドウの作成
        self.window = ttk.Toplevel(parent)
        self.window.title("音楽管理 - メドレー設定")
        self.window.geometry("700x700")
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
        # ttkbootstrapを使用しているため、テーマに基づいたスタイルが自動的に適用されます。
        s = ttk.Style()
        s.configure("MusicHeader.TLabel", font=FONT_HEADER)

    def _create_widgets(self):
        """UI要素を作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.window, padding="15")
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
        list_frame = ttk.Labelframe(
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
        btn_frame = ttk.Frame(list_frame)
        btn_frame.grid(row=0, column=2, sticky="ns", padx=(10, 0))

        ttk.Button(
            btn_frame,
            text="➕ 追加",
            command=self._add_music,
            width=12,
            bootstyle="secondary-outline",
        ).pack(pady=2)
        ttk.Button(
            btn_frame,
            text="🗑️ 削除",
            command=self._remove_music,
            width=12,
            bootstyle="secondary-outline",
        ).pack(pady=2)
        ttk.Button(
            btn_frame,
            text="⬆️ 上へ",
            command=self._move_up,
            width=12,
            bootstyle="secondary-outline",
        ).pack(pady=2)
        ttk.Button(
            btn_frame,
            text="⬇️ 下へ",
            command=self._move_down,
            width=12,
            bootstyle="secondary-outline",
        ).pack(pady=2)
        ttk.Button(
            btn_frame,
            text="🔊 プレビュー",
            command=self._preview_selected,
            width=12,
            bootstyle="secondary-outline",
        ).pack(pady=2)
        ttk.Button(
            btn_frame,
            text="⏹️ 停止",
            command=self._stop_preview,
            width=12,
            bootstyle="secondary-outline",
        ).pack(pady=2)

        # インターバル設定フレーム
        interval_frame = ttk.Labelframe(
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
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=4, column=0, sticky="ew")

        ttk.Button(
            bottom_frame,
            text="✅ 保存して閉じる",
            command=self._save_and_close,
            bootstyle="primary",
        ).pack(side="right", padx=(5, 0))

        ttk.Button(
            bottom_frame,
            text="❌ キャンセル",
            command=self._on_close,
            bootstyle="secondary-outline",
        ).pack(side="right")

        ttk.Button(
            bottom_frame,
            text="🗑️ すべてクリア",
            command=self._clear_all,
            bootstyle="danger-outline",
        ).pack(side="left")

    def _refresh_list(self):
        """リストボックスを更新"""
        self.listbox.delete(0, tk.END)

        for i, music_path in enumerate(self.music_list, 1):
            filename = os.path.basename(music_path)
            self.listbox.insert(tk.END, f"{i}. {filename}")

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

            self._refresh_list()

            # 追加した最初のファイルを選択
            if len(self.music_list) > 0:
                self.listbox.selection_set(len(self.music_list) - len(paths))

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
        self.music_player.play(delay=0)

        # ステータス更新
        filename = os.path.basename(self.music_list[index])
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

        # コールバックを呼び出し（音楽リストとインターバルを渡す）
        self.on_save_callback(self.music_list, interval)

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
