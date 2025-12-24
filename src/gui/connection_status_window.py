import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
import os
import threading
import time


class ConnectionStatusWindow(tk.Toplevel):
    def __init__(self, parent, network_manager, drone_configs):
        super().__init__(parent)
        self.title("Tello 接続ステータス")
        self.geometry("900x700")
        self.network_manager = network_manager
        self.drone_configs = drone_configs  # {name: ip, ...}

        self.img_path = os.path.join(
            os.path.dirname(__file__), "..", "img", "Tello.png"
        )
        self.tello_photo = None
        self._load_image()

        self._create_widgets()
        self.refresh_status()

    def _load_image(self):
        try:
            if os.path.exists(self.img_path):
                img = Image.open(self.img_path)
                # アスペクト比を維持してリサイズ
                max_w = 200
                ratio = max_w / float(img.width)
                new_h = int(float(img.height) * ratio)

                img = img.resize((max_w, new_h), Image.Resampling.LANCZOS)
                self.tello_photo = ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Error loading image: {e}")

    def _create_widgets(self):
        # メインフレーム
        self.main_frame = ttk.Frame(self, padding=20)
        self.main_frame.pack(fill=BOTH, expand=YES)

        # ヘッダー
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=X, pady=(0, 20))

        ttk.Label(
            header_frame,
            text="Tello 接続ステータス",
            font=("Yu Gothic UI", 16, "bold"),
        ).pack(side=LEFT)

        self.refresh_btn = ttk.Button(
            header_frame, text="更新", bootstyle=INFO, command=self.refresh_status
        )
        self.refresh_btn.pack(side=RIGHT)

        # グリッドコンテナ (スクロール可能にする)
        self.canvas = tk.Canvas(
            self.main_frame, highlightthickness=0, bg=self.cget("bg")
        )
        self.scrollbar = ttk.Scrollbar(
            self.main_frame, orient=VERTICAL, command=self.canvas.yview
        )
        self.grid_frame = ttk.Frame(self.canvas)

        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.grid_frame, anchor=NW
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # キャンバスの幅に合わせて内部フレームの幅を調整
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.pack(side=LEFT, fill=BOTH, expand=YES)
        self.scrollbar.pack(side=RIGHT, fill=Y)

        self.grid_frame.bind("<Configure>", self._on_frame_configure)

        # マウスホイール対応 (マウスがキャンバス上にある時のみ有効化)
        self.canvas.bind(
            "<Enter>",
            lambda _: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel),
        )
        self.canvas.bind("<Leave>", lambda _: self.canvas.unbind_all("<MouseWheel>"))

    def _on_canvas_configure(self, event):
        # 内部フレームの幅をキャンバスの幅に合わせる
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_frame_configure(self, event):
        # コンテンツのサイズに合わせてスクロール領域を更新
        bbox = self.canvas.bbox("all")
        if bbox:
            # (0, 0)から始まるように固定し、上方向への不要なスクロールを防止
            self.canvas.configure(scrollregion=(0, 0, bbox[2], bbox[3]))

    def _on_mousewheel(self, event):
        if self.canvas.winfo_exists():
            # コンテンツがキャンバスより大きい場合のみスクロールを許可
            bbox = self.canvas.bbox("all")
            if bbox and bbox[3] > self.canvas.winfo_height():
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh_status(self):
        # 既存のカードを削除
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        # 接続情報を取得
        if self.network_manager:
            connected_tellos = self.network_manager.get_connected_tellos()
        else:
            connected_tellos = []

        # 設定されているドローン一覧
        # drone_configs: {name: ip}

        # 表示用のデータを整理
        display_data = []
        for name, target_ip in self.drone_configs.items():
            # このドローンが現在接続されているか確認
            connection = next(
                (c for c in connected_tellos if c["ip"] == target_ip), None
            )

            display_data.append(
                {
                    "name": name,
                    "target_ip": target_ip,
                    "ssid": connection["ssid"] if connection else "未接続",
                    "interface": connection["interface"] if connection else "-",
                    "connected": connection is not None,
                }
            )

        # Bentoグリッド風に配置
        # ドローンの数に応じて列数を調整
        num_drones = len(display_data)
        if num_drones <= 1:
            cols = 1
        elif num_drones <= 4:
            cols = 2
        else:
            cols = 3

        for i in range(cols):
            self.grid_frame.columnconfigure(i, weight=1)

        for i, data in enumerate(display_data):
            row = i // cols
            col = i % cols

            self._create_card(self.grid_frame, data, row, col)

    def _create_card(self, parent, data, row, col):
        # カードのスタイル
        # Bentoグリッド風に、インデックスによってサイズを変える（オプション）
        # ここではシンプルに、モダンなカードデザインを追求

        card_frame = ttk.Frame(parent, padding=5)
        card_frame.grid(row=row, column=col, padx=10, pady=10, sticky=NSEW)

        # 外枠（影の代わり）
        outer_style = LIGHT if not data["connected"] else SUCCESS
        outer = ttk.Frame(card_frame, bootstyle=outer_style, padding=2)
        outer.pack(fill=BOTH, expand=YES)

        # メインコンテンツ
        inner = ttk.Frame(outer, padding=20, bootstyle=LIGHT)
        inner.pack(fill=BOTH, expand=YES)

        # ステータスバッジ (右上に配置したいが、packなので上に)
        status_frame = ttk.Frame(inner, bootstyle=LIGHT)
        status_frame.pack(fill=X)

        status_text = "● ONLINE" if data["connected"] else "○ OFFLINE"
        status_color = SUCCESS if data["connected"] else SECONDARY
        ttk.Label(
            status_frame,
            text=status_text,
            font=("Yu Gothic UI", 9, "bold"),
            bootstyle=status_color,
        ).pack(side=RIGHT)

        # 画像
        if self.tello_photo:
            img_label = ttk.Label(inner, image=self.tello_photo, bootstyle=LIGHT)
            img_label.pack(pady=10)
        else:
            ttk.Label(
                inner,
                text="[ Tello Image ]",
                font=("Yu Gothic UI", 10, "italic"),
                bootstyle=SECONDARY,
            ).pack(pady=20)

        # テキスト情報
        ttk.Label(
            inner, text=data["name"], font=("Yu Gothic UI", 14, "bold"), bootstyle=DARK
        ).pack()

        info_frame = ttk.Frame(inner, bootstyle=LIGHT, padding=(0, 10, 0, 0))
        info_frame.pack(fill=X)

        # ラベルと値のペア
        self._add_info_row(info_frame, "IP Address:", data["target_ip"])
        self._add_info_row(info_frame, "SSID:", data["ssid"])
        self._add_info_row(info_frame, "Interface:", data["interface"])

    def _add_info_row(self, parent, label, value):
        row = ttk.Frame(parent, bootstyle=LIGHT)
        row.pack(fill=X, pady=2)
        ttk.Label(
            row, text=label, font=("Yu Gothic UI", 9), bootstyle=SECONDARY, width=12
        ).pack(side=LEFT)
        ttk.Label(row, text=value, font=("Consolas", 10), bootstyle=DARK).pack(
            side=LEFT
        )


if __name__ == "__main__":
    # テスト用
    root = ttk.Window(themename="cosmo")
    app = ConnectionStatusWindow(
        root, None, {"Tello_A": "192.168.10.3", "Tello_B": "192.168.10.2"}
    )
    root.mainloop()
