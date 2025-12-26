"""
音源の再生範囲を編集するウィンドウ
"""

import tkinter as tk
import ttkbootstrap as ttk
import os
import threading

from config import (
    COLOR_BACKGROUND,
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_HIGHLIGHT,
    FONT_NORMAL,
    FONT_BOLD_LARGE,
    FONT_HEADER,
)


class MusicRangeEditorWindow:
    """音源の再生範囲を編集するウィンドウクラス"""

    def __init__(self, parent, music_player, music_config, on_save_callback):
        """
        初期化

        Args:
            parent: 親ウィンドウ
            music_player: MusicPlayerインスタンス
            music_config: 編集対象の音楽設定 {"path": "...", "start": 0.0, "end": 0.0}
            on_save_callback: 保存時のコールバック callback(new_config)
        """
        self.parent = parent
        self.music_player = music_player
        self.music_config = music_config.copy()
        self.on_save_callback = on_save_callback

        self.path = music_config["path"]
        self.file_duration = self.music_player.get_music_duration(self.path)

        # 初期値の設定
        self.start_time = tk.DoubleVar(value=music_config.get("start", 0.0))
        # endが0の場合はファイル末尾
        end_val = music_config.get("end", 0.0)
        if end_val <= 0:
            end_val = self.file_duration
        self.end_time = tk.DoubleVar(value=end_val)
        self.dragging = None

        # ウィンドウの作成
        self.window = ttk.Toplevel(parent)
        self.window.title(f"範囲編集 - {os.path.basename(self.path)}")
        self.window.geometry("980x550")
        self.window.minsize(750, 500)

        # モーダル設定
        self.window.transient(parent)
        self.window.grab_set()

        # スタイル設定（絵文字のズレ対策）
        s = ttk.Style()
        btn_font = ("Segoe UI", 11)
        s.configure("TButton", font=btn_font)
        for bstyle in ["primary", "secondary", "success", "info", "warning", "danger"]:
            s.configure(f"{bstyle}.TButton", font=btn_font)
            s.configure(f"{bstyle.capitalize()}.TButton", font=btn_font)
            s.configure(f"{bstyle}.Outline.TButton", font=btn_font)
            s.configure(f"{bstyle.capitalize()}.Outline.TButton", font=btn_font)

        self._create_widgets()

        # 波形データの取得と描画
        self.window.after(100, self._load_waveform)

    def _create_widgets(self):
        """UI要素を作成"""
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill="both", expand=True)

        # ヘッダー
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(
            header_frame, text=f"🎵 {os.path.basename(self.path)}", font=("Segoe UI", 11, "bold")
        ).pack(side="left")

        ttk.Label(
            header_frame,
            text=f"ファイル全体の長さ: {self.file_duration:.2f}秒",
            bootstyle="secondary",
        ).pack(side="right")

        # 波形表示エリア
        self.canvas_frame = ttk.Frame(main_frame)
        self.canvas_frame.pack(fill="both", expand=True, pady=10)

        colors = self.window.style.colors
        self.canvas = tk.Canvas(
            self.canvas_frame,
            bg=colors.inputbg,
            height=200,
            highlightthickness=1,
            highlightbackground=colors.border,
        )
        self.canvas.pack(fill="both", expand=True)

        # キャンバスのイベントバインド
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<Configure>", lambda e: self._draw_all())

        # 編集コントロール
        control_frame = ttk.Labelframe(main_frame, text="範囲設定", padding="15")
        control_frame.pack(fill="x", pady=10)

        # 開始時間
        start_frame = ttk.Frame(control_frame)
        start_frame.pack(side="left", expand=True)
        ttk.Label(start_frame, text="開始位置 (秒):").pack(side="left")
        self.start_entry = ttk.Spinbox(
            start_frame,
            from_=0.0,
            to=self.file_duration,
            increment=0.1,
            textvariable=self.start_time,
            width=10,
            command=self._on_value_change,
        )
        self.start_entry.pack(side="left", padx=5)
        self.start_entry.bind("<KeyRelease>", lambda e: self._on_value_change())

        # 終了時間
        end_frame = ttk.Frame(control_frame)
        end_frame.pack(side="left", expand=True)
        ttk.Label(end_frame, text="終了位置 (秒):").pack(side="left")
        self.end_entry = ttk.Spinbox(
            end_frame,
            from_=0.0,
            to=self.file_duration,
            increment=0.1,
            textvariable=self.end_time,
            width=10,
            command=self._on_value_change,
        )
        self.end_entry.pack(side="left", padx=5)
        self.end_entry.bind("<KeyRelease>", lambda e: self._on_value_change())

        # プレビューボタン
        ttk.Button(
            control_frame,
            text="🔊 範囲を再生",
            command=self._preview_range,
            bootstyle="info-outline",
        ).pack(side="right", padx=5)

        ttk.Button(
            control_frame,
            text="⏹️ 停止",
            command=self._stop_preview,
            bootstyle="secondary-outline",
        ).pack(side="right")

        # 下部ボタン
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=(10, 0))

        ttk.Button(
            bottom_frame,
            text="✅ 決定",
            command=self._save_and_close,
            bootstyle="primary",
            padding=(20, 10),
        ).pack(side="right", padx=(10, 0))

        ttk.Button(
            bottom_frame,
            text="❌ キャンセル",
            command=self.window.destroy,
            bootstyle="secondary-outline",
            padding=(15, 10),
        ).pack(side="right")

    def _load_waveform(self):
        """波形データをロード"""
        # 長さが0の場合は再取得を試みる
        if self.file_duration <= 0:
            self.file_duration = self.music_player.get_music_duration(self.path)
            if self.file_duration > 0:
                # Spinboxの範囲を更新
                self.start_entry.config(to=self.file_duration)
                self.end_entry.config(to=self.file_duration)
                # 初期値が0だった場合は末尾に設定
                if self.end_time.get() <= 0:
                    self.end_time.set(self.file_duration)

        # 1000ポイントで取得
        self.music_player.request_waveform(
            self.path, 1000, callback=lambda _: self.window.after(0, self._draw_all)
        )

    def _draw_all(self):
        """すべてを描画"""
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 10 or height < 10:
            return

        # 波形の描画
        waveform = self.music_player.get_waveform(self.path, 1000)
        if waveform:
            y_mid = height / 2
            draw_h = height * 0.8
            points = []
            # 上半分
            for i, val in enumerate(waveform):
                px = (i / (len(waveform) - 1)) * width
                points.extend([px, y_mid - val * (draw_h / 2)])
            # 下半分
            for i in range(len(waveform) - 1, -1, -1):
                val = waveform[i]
                px = (i / (len(waveform) - 1)) * width
                points.extend([px, y_mid + val * (draw_h / 2)])

            self.canvas.create_polygon(
                points, fill="#d1c4e9", outline="#9575cd", width=1
            )

        # 選択範囲外のマスク
        start_x = (self.start_time.get() / self.file_duration) * width
        end_x = (self.end_time.get() / self.file_duration) * width

        # テーマに応じてマスクの色を変える
        is_dark = self.window.style.theme_use() == "darkly"
        mask_color = "white" if is_dark else "black"

        # 開始前
        self.canvas.create_rectangle(
            0, 0, start_x, height, fill=mask_color, stipple="gray50", outline=""
        )
        # 終了後
        self.canvas.create_rectangle(
            end_x, 0, width, height, fill=mask_color, stipple="gray50", outline=""
        )

        # ハンドル（線）
        self.canvas.create_line(
            start_x, 0, start_x, height, fill=COLOR_ACCENT, width=2, tags="handle_start"
        )
        self.canvas.create_line(
            end_x, 0, end_x, height, fill=COLOR_WARNING, width=2, tags="handle_end"
        )

        # ハンドルのラベル
        self.canvas.create_text(
            start_x + 5,
            10,
            text="START",
            anchor="nw",
            fill=COLOR_ACCENT,
            font=("Arial", 8, "bold"),
        )
        self.canvas.create_text(
            end_x - 5,
            10,
            text="END",
            anchor="ne",
            fill=COLOR_WARNING,
            font=("Arial", 8, "bold"),
        )

    def _on_canvas_click(self, event):
        """キャンバスクリック時の処理"""
        width = self.canvas.winfo_width()
        if width <= 0 or self.file_duration <= 0:
            return

        # クリック位置に近い方のハンドルを選択
        x_time = (event.x / width) * self.file_duration
        dist_start = abs(x_time - self.start_time.get())
        dist_end = abs(x_time - self.end_time.get())

        if dist_start < dist_end:
            self.dragging = "start"
            self.start_time.set(max(0, min(x_time, self.end_time.get() - 0.1)))
        else:
            self.dragging = "end"
            self.end_time.set(
                max(self.start_time.get() + 0.1, min(x_time, self.file_duration))
            )

        self._draw_all()

    def _on_canvas_drag(self, event):
        """キャンバスドラッグ時の処理"""
        width = self.canvas.winfo_width()
        if width <= 0 or self.file_duration <= 0:
            return

        x_time = (event.x / width) * self.file_duration

        if self.dragging == "start":
            self.start_time.set(max(0, min(x_time, self.end_time.get() - 0.1)))
        else:
            self.end_time.set(
                max(self.start_time.get() + 0.1, min(x_time, self.file_duration))
            )

        self._draw_all()

    def _on_value_change(self):
        """数値入力が変更された時の処理"""
        try:
            s = float(self.start_time.get())
            e = float(self.end_time.get())

            # 範囲チェック
            if s < 0:
                s = 0.0
                self.start_time.set(s)
            if e > self.file_duration and self.file_duration > 0:
                e = self.file_duration
                self.end_time.set(e)

            # 整合性チェック（開始は終了より前）
            if s >= e:
                if self.dragging == "start":
                    s = max(0, e - 0.1)
                    self.start_time.set(s)
                else:
                    e = min(
                        self.file_duration if self.file_duration > 0 else s + 100,
                        s + 0.1,
                    )
                    self.end_time.set(e)

            self._draw_all()
        except Exception:
            pass

    def _preview_range(self):
        """選択範囲をプレビュー再生"""
        self.music_player.stop()
        # 少し待ってから再生（停止処理の完了を待つ）
        self.window.after(100, self._start_preview_actual)

    def _start_preview_actual(self):
        """実際のプレビュー再生開始"""
        self.music_player.set_music(self.path, show_log=False)
        self.music_player._play_single(
            delay=0, start_time=self.start_time.get(), end_time=self.end_time.get()
        )

    def _stop_preview(self):
        """プレビュー停止"""
        self.music_player.stop()

    def _save_and_close(self):
        """設定を保存して閉じる"""
        self.music_config["start"] = self.start_time.get()
        # ファイル末尾の場合は0にする（またはそのまま保持）
        if abs(self.end_time.get() - self.file_duration) < 0.01:
            self.music_config["end"] = 0.0
        else:
            self.music_config["end"] = self.end_time.get()

        self.on_save_callback(self.music_config)
        self.window.destroy()
