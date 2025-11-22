import sys
import zipfile
import json
import time
import math
import socket
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from queue import Queue

# -----------------------------------------------------------------------------
# ■■■ 設定と定数 ■■■
# -----------------------------------------------------------------------------
CONFIG_FILE = "tello_config.json"
SCRATCH_TO_CM_RATE = 1
MIN_TELLO_MOVE = 20
INITIAL_HOVER_HEIGHT_CM = 80
TELLO_HORIZONTAL_SPEED_CMS = 50.0
TELLO_VERTICAL_SPEED_CMS = 40.0


# -----------------------------------------------------------------------------
# ■■■ Tello制御クラス ■■■
# -----------------------------------------------------------------------------
class TelloController:
    """Telloドローンとの通信を管理するクラス"""

    def __init__(self, pc_ip, name, port_offset, log_queue):
        """
        コントローラーの初期化

        Args:
            pc_ip: PC側のIPアドレス
            name: ドローンの識別名
            port_offset: ポート番号のオフセット
            log_queue: ログキュー
        """
        self.name = name
        self.log_queue = log_queue
        self.tello_address = ("192.168.10.1", 8889)
        self.pc_address = (pc_ip, 9000 + port_offset)

        # UDPソケットの作成とバインド
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(self.pc_address)

        # 応答受信用のスレッド設定
        self.response = None
        self.stop_event = threading.Event()
        self.response_thread = threading.Thread(target=self._receive_response)
        self.response_thread.daemon = True
        self.response_thread.start()

        self.log(
            {"level": "INFO", "message": f"[{self.name}] コントローラー初期化完了。"}
        )

    def log(self, log_item):
        """ログをキューに追加"""
        self.log_queue.put(log_item)

    def _receive_response(self):
        """Telloからの応答を受信するスレッド"""
        while not self.stop_event.is_set():
            try:
                data, _ = self.socket.recvfrom(1024)
                self.response = data.decode("utf-8").strip()
            except Exception:
                break

    def send_command(self, command, timeout=7):
        """
        Telloにコマンドを送信し、応答を待つ

        Args:
            command: 送信するコマンド文字列
            timeout: タイムアウト時間（秒）

        Returns:
            bool: コマンドが正常に実行されたかどうか
        """
        self.response = None
        self.log({"level": "INFO", "message": f"[{self.name}] 送信: {command}"})
        self.socket.sendto(command.encode("utf-8"), self.tello_address)

        start_time = time.time()
        while self.response is None:
            if self.stop_event.is_set():
                self.log(
                    {
                        "level": "WARNING",
                        "message": f"[{self.name}] 停止イベントによりコマンドキャンセル。",
                    }
                )
                return False

            if time.time() - start_time > timeout:
                self.log(
                    {
                        "level": "ERROR",
                        "message": f"[{self.name}] '{command}' の応答待機中にタイムアウト。",
                    }
                )
                return False

            time.sleep(0.1)

        # 応答の評価
        if "ok" in self.response or command.startswith("land"):
            self.log({"level": "SUCCESS", "message": f"[{self.name}] 応答: OK"})
            return True
        else:
            self.log(
                {"level": "WARNING", "message": f"[{self.name}] 応答: {self.response}"}
            )
            return False

    def close(self):
        """コントローラーを終了し、リソースを解放"""
        self.stop_event.set()
        self.socket.close()
        self.response_thread.join(timeout=1)
        self.log(
            {"level": "INFO", "message": f"[{self.name}] コントローラーを閉じました。"}
        )


# -----------------------------------------------------------------------------
# ■■■ Scratchプロジェクト解析クラス ■■■
# -----------------------------------------------------------------------------
class ScratchProjectParser:
    """Scratchプロジェクトファイル(.sb3)を解析してTelloコマンドのスケジュールを生成"""

    def __init__(self, sb3_path, log_queue):
        """
        パーサーの初期化

        Args:
            sb3_path: Scratchプロジェクトファイル(.sb3)のパス
            log_queue: ログキュー
        """
        self.sb3_path = sb3_path
        self.log_queue = log_queue
        self.project_data = self._load_project_data()
        self.has_any_valid_action = False

    def log(self, message, level="INFO"):
        """ログをキューに追加"""
        self.log_queue.put({"level": level, "message": message})

    def _load_project_data(self):
        """Scratchプロジェクトファイルからproject.jsonを読み込む"""
        try:
            with zipfile.ZipFile(self.sb3_path, "r") as z:
                with z.open("project.json") as f:
                    return json.load(f)
        except Exception as e:
            self.log(
                f"エラー: {self.sb3_path} の読み込みまたは解析に失敗しました。 -> {e}",
                level="ERROR",
            )
            return None

    def _get_input_value(self, block_input, blocks):
        """
        ブロックの入力値を取得

        Args:
            block_input: ブロックの入力データ
            blocks: 全ブロックの辞書

        Returns:
            float or None: 入力値（取得できない場合はNone）
        """
        if not block_input:
            return None

        # 直接値が指定されている場合
        if block_input[0] == 1 and isinstance(block_input[1], list):
            return float(block_input[1][1])

        # 他のブロックを参照している場合
        elif block_input[0] == 1 and isinstance(block_input[1], str):
            ref_block = blocks.get(block_input[1])
            if ref_block and ref_block["opcode"] == "math_number":
                return float(ref_block["fields"]["NUM"][0])

        return None

    def _parse_sprite_to_actions(self, sprite_name, blocks):
        """スプライトのブロックをアクションシーケンスに変換"""
        action_sequence = []
        start_block_id = self._find_start_block(blocks)

        if not start_block_id:
            return []

        self.has_any_valid_action = True

        # 初期位置の設定
        pos_x, pos_y = 0, 0
        pos_z = INITIAL_HOVER_HEIGHT_CM

        # ブロックを順番に処理
        block_id = start_block_id
        while block_id:
            block = blocks.get(block_id)
            if not block:
                break

            opcode = block.get("opcode")
            inputs = block.get("inputs", {})

            # アクション情報の初期化
            action = {
                "duration": 0.0,
                "commands": [],
                "warnings": [],
                "is_wait": False,
                "sprite_name": sprite_name,
            }

            # オペコードごとの処理
            if opcode == "motion_gotoxy":
                # x,y座標への移動
                val_x = self._get_input_value(inputs.get("X"), blocks)
                val_y = self._get_input_value(inputs.get("Y"), blocks)
                if val_x is not None and val_y is not None:
                    action["commands"], action["duration"], action["warnings"] = (
                        self._pos_to_commands(sprite_name, pos_x, pos_y, val_x, val_y)
                    )
                    pos_x, pos_y = val_x, val_y

            elif opcode == "motion_movesteps":
                # 指定歩数の移動
                steps = self._get_input_value(inputs.get("STEPS"), blocks)
                if steps is not None:
                    rad = math.radians(90 - 90)
                    new_x = pos_x + steps * math.sin(rad)
                    new_y = pos_y + steps * math.cos(rad)
                    action["commands"], action["duration"], action["warnings"] = (
                        self._pos_to_commands(sprite_name, pos_x, pos_y, new_x, new_y)
                    )
                    pos_x, pos_y = new_x, new_y

            elif opcode == "control_wait":
                # 待機
                duration = self._get_input_value(inputs.get("DURATION"), blocks)
                if duration is not None:
                    action["duration"] = duration
                    action["is_wait"] = True

            elif opcode == "looks_setsizeto":
                # 大きさの設定（高度）
                size = self._get_input_value(inputs.get("SIZE"), blocks)
                if size is not None:
                    action["commands"], action["duration"], action["warnings"] = (
                        self._height_to_commands(sprite_name, pos_z, size)
                    )
                    pos_z = size

            elif opcode == "looks_changesizeby":
                # 大きさの変更（高度変化）
                change = self._get_input_value(inputs.get("CHANGE"), blocks)
                if change is not None:
                    new_z = pos_z + change
                    action["commands"], action["duration"], action["warnings"] = (
                        self._height_to_commands(sprite_name, pos_z, new_z)
                    )
                    pos_z = new_z

            elif (
                opcode == "control_stop"
                and block.get("fields", {}).get("STOP_OPTION", [None])[0] == "all"
            ):
                # すべてを止める
                action["commands"].append({"target": "system", "command": "stop_all"})

            action_sequence.append(action)
            block_id = block.get("next")

        return action_sequence

    def parse_to_schedule(self):
        """プロジェクトデータから実行スケジュールを生成"""
        if not self.project_data:
            return [], 0.0

        # 各スプライトのアクションを解析
        all_actions = {}
        for target in self.project_data.get("targets", []):
            if target.get("isStage", False):
                continue

            sprite_name = target.get("name")
            blocks = target.get("blocks", {})
            all_actions[sprite_name] = self._parse_sprite_to_actions(
                sprite_name, blocks
            )

        # タイムラインの構築
        final_event_list = []
        master_time = 0.0

        while any(all_actions.values()):
            max_duration_this_step = 0.0
            actions_this_step = []

            # 各スプライトから次のアクションを取得
            for sprite_name, action_list in all_actions.items():
                if action_list:
                    action = action_list.pop(0)
                    actions_this_step.append(action)
                    max_duration_this_step = max(
                        max_duration_this_step, action["duration"]
                    )

            # アクションをイベントリストに変換
            for action in actions_this_step:
                # 待機時間の警告
                if action["is_wait"] and action["duration"] < max_duration_this_step:
                    msg = (
                        f"[{action['sprite_name']}] 待機時間({action['duration']:.2f}秒)が"
                        f"ステップ最長動作({max_duration_this_step:.2f}秒)より短いため、待機が延長されます。"
                    )
                    final_event_list.append(
                        {"time": master_time, "type": "WARNING", "text": msg}
                    )

                # 待機イベントの追加
                if action["is_wait"]:
                    final_event_list.append(
                        {
                            "time": master_time,
                            "type": "WAIT",
                            "target": action["sprite_name"],
                            "text": f"{action['duration']:.2f}秒 待機",
                        }
                    )

                # コマンドイベントの追加
                for cmd in action["commands"]:
                    cmd["time"] = master_time
                    cmd["type"] = "COMMAND"
                    final_event_list.append(cmd)

                # 警告メッセージの追加
                for warning_msg in action["warnings"]:
                    final_event_list.append(
                        {"time": master_time, "type": "WARNING", "text": warning_msg}
                    )

            master_time += max_duration_this_step

        # 時間順にソート（警告を先に表示）
        final_event_list.sort(
            key=lambda x: (x["time"], 0 if x["type"] == "WARNING" else 1)
        )
        return final_event_list, master_time

    def _find_start_block(self, blocks):
        """「緑の旗が押されたとき」ブロックを探す"""
        for block_id, block in blocks.items():
            if block.get("opcode") == "event_whenflagclicked":
                return block.get("next")
        return None

    def _pos_to_commands(self, name, x1, y1, x2, y2):
        """位置の変化をTelloコマンドに変換"""
        cmds = []
        warnings = []

        # 移動量の計算
        dx = int((x2 - x1) * SCRATCH_TO_CM_RATE)
        dy = int((y2 - y1) * SCRATCH_TO_CM_RATE)
        duration = 0.0

        # 最小移動量のチェック
        if 0 < abs(dx) < MIN_TELLO_MOVE:
            warnings.append(
                f"[{name}] 水平移動 {abs(dx)}cmは小さすぎるため無視されました。(最小{MIN_TELLO_MOVE}cm)"
            )
        if 0 < abs(dy) < MIN_TELLO_MOVE:
            warnings.append(
                f"[{name}] 前後移動 {abs(dy)}cmは小さすぎるため無視されました。(最小{MIN_TELLO_MOVE}cm)"
            )

        # 水平移動コマンドの生成
        if abs(dx) >= MIN_TELLO_MOVE:
            direction = "right" if dx > 0 else "left"
            cmds.append({"target": name, "command": f"{direction} {abs(dx)}"})
            duration = max(duration, abs(dx) / TELLO_HORIZONTAL_SPEED_CMS)

        # 前後移動コマンドの生成
        if abs(dy) >= MIN_TELLO_MOVE:
            direction = "forward" if dy > 0 else "back"
            cmds.append({"target": name, "command": f"{direction} {abs(dy)}"})
            duration = max(duration, abs(dy) / TELLO_HORIZONTAL_SPEED_CMS)

        return cmds, duration, warnings

    def _height_to_commands(self, name, z1, z2):
        """高度の変化をTelloコマンドに変換"""
        cmds = []
        warnings = []

        # 高度変化量の計算
        dz = int(z2 - z1)
        duration = 0.0

        # 最小移動量のチェック
        if 0 < abs(dz) < MIN_TELLO_MOVE:
            warnings.append(
                f"[{name}] 高さ変更 {abs(dz)}cmは小さすぎるため無視されました。(最小{MIN_TELLO_MOVE}cm)"
            )

        # 上下移動コマンドの生成
        if abs(dz) >= MIN_TELLO_MOVE:
            direction = "up" if dz > 0 else "down"
            cmds.append({"target": name, "command": f"{direction} {abs(dz)}"})
            duration = max(duration, abs(dz) / TELLO_VERTICAL_SPEED_CMS)

        return cmds, duration, warnings


# -----------------------------------------------------------------------------
# ■■■ ドローンショー実行ワーカー関数 ■■■
# -----------------------------------------------------------------------------
def run_show_worker(drones_config, schedule, stop_event, log_queue, total_time):
    """ドローンショーを実行するワーカー関数（別スレッドで実行）"""
    controllers = {}

    try:
        # UIのハイライトをクリア
        log_queue.put({"type": "clear_highlight"})
        log_queue.put(
            {
                "level": "INFO",
                "message": "--- ドローンコントローラーを初期化しています... ---",
            }
        )

        # スケジュールに含まれるドローンを特定
        drone_names_in_schedule = set(
            evt["target"] for evt in schedule if evt.get("type") in ["COMMAND", "WAIT"]
        )

        # 必要なドローンのコントローラーを初期化
        for i, config in enumerate(drones_config):
            if config["name"] in drone_names_in_schedule or any(
                cmd.get("command") == "stop_all" for cmd in schedule
            ):
                controllers[config["name"]] = TelloController(
                    config["pc_ip"], config["name"], i, log_queue
                )

        if not controllers and schedule:
            log_queue.put(
                {
                    "level": "WARNING",
                    "message": "Scratchファイルに制御対象のドローンが見つかりませんでした。",
                }
            )
            return

        # 初期コマンドの実行（command, takeoff）
        initial_commands = ["command", "takeoff"]
        for command in initial_commands:
            if stop_event.is_set():
                break

            log_queue.put(
                {"level": "INFO", "message": f"\n--- 初期コマンドを実行: {command} ---"}
            )

            # 全ドローンに同時にコマンドを送信
            threads = [
                threading.Thread(target=c.send_command, args=(command,))
                for c in controllers.values()
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # 待機時間
            wait_time = 5 if command == "takeoff" else 2
            time.sleep(wait_time)

        if stop_event.is_set():
            raise threading.ThreadError("離陸中に停止イベントが発生しました。")

        # スケジュールの実行開始
        start_time = time.time()
        all_event_times = sorted(list(set(evt["time"] for evt in schedule)))

        for exec_time in all_event_times:
            if stop_event.is_set():
                break

            # 次のイベントまで待機
            wait_time = (start_time + exec_time) - time.time()
            if wait_time > 0:
                time.sleep(wait_time)

            if stop_event.is_set():
                break

            # UIで現在のステップをハイライト
            log_queue.put({"type": "highlight", "time": exec_time})
            log_queue.put(
                {
                    "level": "INFO",
                    "message": f"\n--- ステップ開始 ( {exec_time:.2f}秒地点 ) ---",
                }
            )

            # この時刻に実行するイベントを集める
            threads = []
            events_to_run = [evt for evt in schedule if evt.get("time") == exec_time]

            for event in events_to_run:
                if event["type"] == "WAIT":
                    log_queue.put(
                        {
                            "level": "INFO",
                            "message": f"--- {event['target']} | {event['text']} ---",
                        }
                    )

                elif event["type"] == "COMMAND":
                    cmd = event

                    # 「すべてを止める」命令の処理
                    if cmd.get("command") == "stop_all":
                        log_queue.put(
                            {
                                "level": "INFO",
                                "message": "--- Scratchからの「すべてを止める」命令を検知しました。 ---",
                            }
                        )
                        stop_event.set()
                        break

                    target = cmd["target"]
                    command = cmd["command"]

                    if target in controllers:
                        thread = threading.Thread(
                            target=controllers[target].send_command, args=(command,)
                        )
                        threads.append(thread)

            if stop_event.is_set():
                break

            # コマンド送信スレッドを一斉に開始（完了は待たない）
            for t in threads:
                t.start()

        # 最終待機時間
        end_wait_time = (start_time + total_time) - time.time()
        if end_wait_time > 0 and not stop_event.is_set():
            log_queue.put(
                {
                    "level": "INFO",
                    "message": f"\n--- 最終ステップ完了。{end_wait_time:.2f}秒後に着陸します... ---",
                }
            )
            time.sleep(end_wait_time)

        if not stop_event.is_set():
            log_queue.put(
                {
                    "level": "INFO",
                    "message": "\n--- ショーが完了しました。着陸します... ---",
                }
            )

    except Exception as e:
        log_queue.put(
            {
                "level": "ERROR",
                "message": f"\n--- 実行中にエラーが発生しました: {e} ---",
            }
        )
        log_queue.put({"level": "ERROR", "message": traceback.format_exc()})

    finally:
        # クリーンアップ処理
        log_queue.put({"type": "clear_highlight"})
        log_queue.put(
            {
                "level": "INFO",
                "message": "\n--- 全てのドローンを着陸させています... ---",
            }
        )

        # 全ドローンに着陸コマンドを送信
        threads = [
            threading.Thread(target=c.send_command, args=("land", 5))
            for c in controllers.values()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 全接続をクローズ
        for c in controllers.values():
            c.close()

        log_queue.put({"level": "INFO", "message": "--- 全ての接続を閉じました。 ---"})


# -----------------------------------------------------------------------------
# ■■■ メインGUIアプリケーションクラス ■■■
# -----------------------------------------------------------------------------
class TelloApp:
    """メインGUIアプリケーションクラス"""

    def __init__(self, master):
        """アプリケーションの初期化"""
        self.master = master
        self.master.title("Tello Scratch ドローンショー・コントローラー")
        self.master.geometry("900x650")
        self.master.minsize(800, 500)
        self.master.configure(bg="#f0f0f0")

        # フォント設定
        self.font_normal = ("Yu Gothic UI", 10)
        self.font_bold_large = ("Yu Gothic UI", 12, "bold")
        self.font_header = ("Yu Gothic UI", 10, "bold")
        self.font_monospace = ("Consolas", 10)

        # スタイル設定
        self._configure_styles()

        # 状態変数の初期化
        self.drone_entry_widgets = []
        self.schedule = None
        self.total_time = 0.0
        self.time_to_line_map = {}
        self.last_highlighted_lines = None
        self.sb3_path = tk.StringVar()
        self.show_status = tk.StringVar(value="準備完了")
        self.log_queue = Queue()
        self.show_thread = None
        self.stop_event = threading.Event()

        # UI構築と初期化
        self._create_widgets()
        self.load_config()
        self.process_log_queue()

    def _configure_styles(self):
        """UI要素のスタイルを設定"""
        s = ttk.Style()
        s.theme_use("clam")

        # 基本スタイル
        s.configure("TFrame", background="#f0f0f0")
        s.configure(
            "TLabel", background="#f0f0f0", foreground="black", font=self.font_normal
        )
        s.configure("Header.TLabel", font=self.font_header, foreground="#0078D7")

        # LabelFrame
        s.configure("TLabelframe", background="#f0f0f0")
        s.configure("TLabelframe.Label", font=self.font_bold_large, foreground="#333")

        # ボタン
        s.configure("TButton", font=self.font_normal, padding=6)
        s.configure(
            "Accent.TButton",
            font=self.font_normal,
            padding=8,
            foreground="white",
            background="#0078D7",
        )
        s.map("Accent.TButton", background=[("active", "#005f9e")])
        s.configure(
            "Stop.TButton",
            font=self.font_normal,
            padding=8,
            foreground="white",
            background="#d13438",
        )
        s.map("Stop.TButton", background=[("active", "#a4262c")])

    def _create_widgets(self):
        main_frame = ttk.Frame(self.master, padding="15")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 15))
        left_frame.grid_rowconfigure(2, weight=1)
        ip_frame = ttk.LabelFrame(left_frame, text="① ドローンの設定", padding="10")
        ip_frame.pack(fill="x", pady=(0, 15))
        self.ip_entry_frame = ttk.Frame(ip_frame)
        self.ip_entry_frame.pack(fill="x")
        ip_button_frame = ttk.Frame(ip_frame)
        ip_button_frame.pack(fill="x", pady=(10, 5))
        ttk.Button(ip_button_frame, text="＋ 追加", command=self.add_drone_entry).pack(
            side="left", expand=True, fill="x", padx=(0, 2)
        )
        ttk.Button(
            ip_button_frame, text="－ 削除", command=self.remove_drone_entry
        ).pack(side="left", expand=True, fill="x", padx=(2, 0))
        ttk.Button(ip_frame, text="⚙️ 設定を保存", command=self.save_config).pack(
            fill="x", pady=(10, 0)
        )
        file_frame = ttk.LabelFrame(left_frame, text="② プロジェクト選択", padding="10")
        file_frame.pack(fill="x", pady=(0, 15))
        self.sb3_path_label = ttk.Label(
            file_frame, text="ファイルが選択されていません", wraplength=230
        )
        self.sb3_path_label.pack(fill="x", pady=(0, 10))
        ttk.Button(
            file_frame, text="📂 Scratchファイルを開く", command=self.select_file
        ).pack(fill="x")
        action_frame = ttk.LabelFrame(left_frame, text="③ ショー実行", padding="10")
        action_frame.pack(fill="x")
        self.parse_btn = ttk.Button(
            action_frame,
            text="🔄 タイムラインを解析",
            command=self.parse_scratch_project,
            state="disabled",
        )
        self.parse_btn.pack(fill="x", pady=(0, 5))
        self.start_btn = ttk.Button(
            action_frame,
            text="▶️ ショーを開始",
            command=self.start_show,
            state="disabled",
            style="Accent.TButton",
        )
        self.start_btn.pack(fill="x", pady=(5, 5))
        self.stop_btn = ttk.Button(
            action_frame,
            text="⏹️ 緊急停止",
            command=self.emergency_stop,
            state="disabled",
            style="Stop.TButton",
        )
        self.stop_btn.pack(fill="x", pady=(5, 0))
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)
        status_bar = ttk.Frame(main_frame, padding=(5, 5))
        status_bar.grid(row=0, column=1, sticky="ew", pady=(0, 5))
        ttk.Label(status_bar, text="ステータス:", style="Header.TLabel").pack(
            side="left"
        )
        ttk.Label(status_bar, textvariable=self.show_status).pack(side="left", padx=5)
        log_pane = ttk.PanedWindow(right_frame, orient="horizontal")
        log_pane.pack(fill="both", expand=True)
        timeline_frame = ttk.Frame(log_pane, width=400)
        ttk.Label(timeline_frame, text="タイムライン", style="Header.TLabel").pack(
            anchor="w", padx=5
        )
        self.schedule_text = scrolledtext.ScrolledText(
            timeline_frame,
            state="disabled",
            wrap="none",
            height=10,
            font=self.font_monospace,
        )
        self.schedule_text.pack(expand=True, fill="both", padx=5, pady=(0, 5))
        log_pane.add(timeline_frame, weight=1)
        log_frame = ttk.Frame(log_pane, width=200)
        ttk.Label(log_frame, text="通信ログ", style="Header.TLabel").pack(
            anchor="w", padx=5
        )
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            state="disabled",
            wrap="none",
            height=10,
            font=self.font_monospace,
        )
        self.log_text.pack(expand=True, fill="both", padx=5, pady=(0, 5))
        log_pane.add(log_frame, weight=1)
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("SUCCESS", foreground="#28a745")
        self.log_text.tag_config("WARNING", foreground="#ffc107")
        self.log_text.tag_config("ERROR", foreground="#dc3545")
        self.schedule_text.tag_config("INFO", foreground="black")
        self.schedule_text.tag_config("WAIT", foreground="blue")
        self.schedule_text.tag_config("WARNING", foreground="#dc3545")
        self.schedule_text.tag_config(
            "HEADER", foreground="#0078D7", font=self.font_header
        )
        self.schedule_text.tag_config("HIGHLIGHT", background="#d0e9f8")

    def add_drone_entry(self, name=None, ip=""):
        """ドローンの設定エントリを追加"""
        drone_count = len(self.drone_entry_widgets)
        if name is None:
            name = f"Tello_{chr(65 + drone_count)}"

        # ウィジェットの作成
        widget_dict = {}
        row_frame = ttk.Frame(self.ip_entry_frame)
        row_frame.pack(fill="x", pady=2)

        label = ttk.Label(row_frame, text=f"{name}:")
        label.pack(side="left", padx=(0, 5))

        entry = ttk.Entry(row_frame)
        entry.pack(side="left", expand=True, fill="x")
        entry.insert(0, ip)

        widget_dict["name"] = name
        widget_dict["frame"] = row_frame
        widget_dict["ip_widget"] = entry
        self.drone_entry_widgets.append(widget_dict)

    def remove_drone_entry(self):
        """最後のドローン設定エントリを削除"""
        if not self.drone_entry_widgets:
            return

        widgets_to_remove = self.drone_entry_widgets.pop()
        widgets_to_remove["frame"].destroy()

    def load_config(self):
        """設定ファイルからドローン設定を読み込む"""
        try:
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)

            # 既存のエントリをクリア
            while self.drone_entry_widgets:
                self.remove_drone_entry()

            # 設定からエントリを追加
            for name, ip in config_data.items():
                self.add_drone_entry(name=name, ip=ip)

            self.log(
                {
                    "level": "INFO",
                    "message": f"{CONFIG_FILE} から設定を読み込みました。",
                }
            )

        except FileNotFoundError:
            self.log(
                {
                    "level": "WARNING",
                    "message": "設定ファイルが見つかりません。ドローンを１台以上IPアドレスを入力し、保存してください。",
                }
            )
            if not self.drone_entry_widgets:
                self.add_drone_entry()

        except Exception as e:
            self.log({"level": "ERROR", "message": f"設定の読み込みエラー: {e}"})

    def save_config(self):
        """ドローン設定をファイルに保存"""
        config_data = {
            widgets["name"]: widgets["ip_widget"].get()
            for widgets in self.drone_entry_widgets
        }

        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config_data, f, indent=4)

            self.log(
                {"level": "INFO", "message": f"{CONFIG_FILE} に設定を保存しました。"}
            )
            messagebox.showinfo("成功", "IPアドレスを保存しました。")

        except Exception as e:
            messagebox.showerror("エラー", f"設定の保存に失敗しました: {e}")

    def select_file(self):
        """Scratchプロジェクトファイルを選択"""
        path = filedialog.askopenfilename(
            title="Scratch 3 プロジェクトファイルを選択",
            filetypes=[("Scratch プロジェクト", "*.sb3")],
        )

        if path:
            self.sb3_path.set(path)
            self.sb3_path_label.configure(text=path.split("/")[-1])
            self.parse_btn["state"] = "normal"
            self.log({"level": "INFO", "message": f"選択されたファイル: {path}"})
            self.show_status.set(f"ファイル選択済み: {path.split('/')[-1]}")

    def parse_scratch_project(self):
        path = self.sb3_path.get()
        if not path:
            return
        for widget in [self.schedule_text, self.log_text]:
            widget.config(state="normal")
            widget.delete(1.0, tk.END)
            widget.config(state="disabled")
        parser = ScratchProjectParser(path, self.log_queue)
        self.schedule, self.total_time = parser.parse_to_schedule()
        self.schedule_text.config(state="normal")
        self.schedule_text.delete(1.0, tk.END)
        self.time_to_line_map = {}
        if self.schedule or parser.has_any_valid_action:
            self.schedule_text.insert(
                tk.END,
                f"--- 生成されたタイムライン (予想総時間: {self.total_time:.2f}秒) ---\n\n",
                "HEADER",
            )
            current_line = 3
            grouped_events = {}
            for event in self.schedule:
                if event["time"] not in grouped_events:
                    grouped_events[event["time"]] = []
                grouped_events[event["time"]].append(event)
            for time, events in sorted(grouped_events.items()):
                start_line = current_line
                for event in events:
                    evt_type = event.get("type", "COMMAND")
                    if evt_type == "COMMAND":
                        log_msg = f"{time: >6.2f}s | {event.get('target', 'N/A'): <8} | 実行: {event.get('command', '')}\n"
                        self.schedule_text.insert(tk.END, log_msg, "INFO")
                    elif evt_type == "WAIT":
                        log_msg = f"{time: >6.2f}s | {event.get('target', 'N/A'): <8} | 待機: {event.get('text', '')}\n"
                        self.schedule_text.insert(tk.END, log_msg, "WAIT")
                    elif evt_type == "WARNING":
                        log_msg = f"{time: >6.2f}s | {event.get('text', '')}\n"
                        self.schedule_text.insert(tk.END, log_msg, "WARNING")
                    current_line += 1
                end_line = current_line - 1
                self.time_to_line_map[time] = {"start": start_line, "end": end_line}
            self.log(
                {
                    "level": "INFO",
                    "message": "解析に成功しました。ショーを開始できます。",
                }
            )
            self.start_btn["state"] = "normal"
            self.show_status.set(f"解析完了 (予想時間: {self.total_time:.2f}秒)")
        else:
            self.schedule_text.insert(
                tk.END,
                "ファイルから有効なスケジュールを生成できませんでした。\n",
                "ERROR",
            )
            self.schedule_text.insert(
                tk.END,
                "ヒント: スプライトに「緑の旗が押されたとき」ブロックがありますか？\n",
                "INFO",
            )
            self.show_status.set("解析失敗")
        self.schedule_text.config(state="disabled")

    def start_show(self):
        drones_config = [
            {"name": w["name"], "pc_ip": w["ip_widget"].get()}
            for w in self.drone_entry_widgets
        ]
        if not all(c["pc_ip"] for c in drones_config):
            messagebox.showerror(
                "エラー", "開始前に、すべてのIPアドレスを入力してください。"
            )
            return
        self.start_btn["state"] = "disabled"
        self.parse_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"
        self.stop_event.clear()
        self.show_status.set("ショー実行中...")
        self.show_thread = threading.Thread(
            target=run_show_worker,
            args=(
                drones_config,
                self.schedule,
                self.stop_event,
                self.log_queue,
                self.total_time,
            ),
        )
        self.show_thread.start()

    def emergency_stop(self):
        self.log(
            {
                "level": "ERROR",
                "message": "\n!!! ユーザーによる緊急停止が要求されました !!!",
            }
        )
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self.start_btn["state"] = "normal"
        self.parse_btn["state"] = "normal"
        self.show_status.set("緊急停止 - 着陸中")

    def log(self, log_item):
        self.log_queue.put(log_item)

    def process_log_queue(self):
        try:
            while not self.log_queue.empty():
                log_item = self.log_queue.get_nowait()
                if isinstance(log_item, dict) and "type" in log_item:
                    if log_item["type"] == "highlight":
                        self.update_timeline_highlight(log_item.get("time"))
                        continue
                    elif log_item["type"] == "clear_highlight":
                        self.update_timeline_highlight(None)
                        continue
                if isinstance(log_item, dict):
                    level = log_item.get("level", "INFO")
                    message = log_item.get("message", "")
                else:
                    level = "INFO"
                    message = str(log_item)
                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, message + "\n", level)
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")
        finally:
            self.master.after(100, self.process_log_queue)

    def update_timeline_highlight(self, current_time):
        self.schedule_text.config(state="normal")
        if self.last_highlighted_lines:
            self.schedule_text.tag_remove(
                "HIGHLIGHT",
                f"{self.last_highlighted_lines['start']}.0",
                f"{self.last_highlighted_lines['end']}.end",
            )
            self.last_highlighted_lines = None
        if current_time is not None and current_time in self.time_to_line_map:
            line_info = self.time_to_line_map[current_time]
            self.schedule_text.tag_add(
                "HIGHLIGHT", f"{line_info['start']}.0", f"{line_info['end']}.end"
            )
            self.schedule_text.see(f"{line_info['start']}.0")
            self.last_highlighted_lines = line_info
        self.schedule_text.config(state="disabled")

    def on_closing(self):
        if self.show_thread and self.show_thread.is_alive():
            if messagebox.askyesno(
                "終了確認", "ショーが実行中です。停止して終了しますか？"
            ):
                self.emergency_stop()
                self.master.destroy()
        else:
            self.master.destroy()


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    app = TelloApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
