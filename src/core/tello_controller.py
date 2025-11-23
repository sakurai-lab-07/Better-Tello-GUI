"""
Telloドローン制御モジュール
ステータス受信機能付き
"""

import socket
import threading
import time


class TelloController:
    """Telloドローンとの通信・状態管理を行うクラス"""

    def __init__(
        self,
        pc_ip,
        name,
        port_offset,
        log_queue,
        tello_ip="192.168.10.1",
        tello_port=8889,
    ):
        """
        コントローラーの初期化

        Args:
            pc_ip: PC側のIPアドレス（ドングル側のIP）
            name: ドローンの識別名
            port_offset: ポート番号のオフセット
            log_queue: ログキュー
            tello_ip: TelloのIPアドレス
            tello_port: Telloのポート番号
        """
        self.name = name
        self.log_queue = log_queue
        self.tello_address = (tello_ip, tello_port)
        self.pc_address = (pc_ip, 9000 + port_offset)
        self.pc_ip = pc_ip

        # --- 1. コマンド送信用ソケット (Port: 9000+offset) ---
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(self.pc_address)

        # --- 2. ステータス受信用ソケット (Port: 8890) ---
        # Telloはステータス情報を常にポート8890に送ってくる
        self.state_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 複数のインターフェースがある場合、それぞれのIPの8890にバインドする
        try:
            self.state_socket.bind((self.pc_ip, 8890))
        except Exception as e:
            self.log({"level": "ERROR", "message": f"[{self.name}] State Bind Error: {e}"})

        # 状態保持用辞書
        self.state = {
            "bat": 0,      # バッテリー残量 (%)
            "h": 0,        # 高さ (cm)
            "temp": 0,     # 温度 (℃)
            "active": False, # 通信が生きているか
            "last_update": 0 # 最終更新時刻
        }

        # スレッド制御
        self.response = None
        self.stop_event = threading.Event()
        
        # コマンド応答受信スレッド
        self.response_thread = threading.Thread(target=self._receive_response)
        self.response_thread.daemon = True
        self.response_thread.start()

        # ステータス受信スレッド
        self.state_thread = threading.Thread(target=self._receive_state)
        self.state_thread.daemon = True
        self.state_thread.start()

    def log(self, log_item):
        """ログをキューに追加"""
        if self.log_queue:
            self.log_queue.put(log_item)

    def get_state(self):
        """現在の状態を返す"""
        # 最終更新から3秒以上経過していたら通信ロストとみなす
        if time.time() - self.state["last_update"] > 3.0:
            self.state["active"] = False
        else:
            self.state["active"] = True
        return self.state

    def _receive_response(self):
        """コマンドへの応答を受信するループ"""
        while not self.stop_event.is_set():
            try:
                data, _ = self.socket.recvfrom(1024)
                self.response = data.decode("utf-8").strip()
            except Exception:
                break

    def _receive_state(self):
        """Telloからのステータスを受信・解析するループ"""
        while not self.stop_event.is_set():
            try:
                data, _ = self.state_socket.recvfrom(2048)
                state_str = data.decode("utf-8").strip()
                self._parse_state(state_str)
            except Exception:
                break

    def _parse_state(self, state_str):
        """
        ステータス文字列を解析して辞書を更新
        例: "pitch:0;roll:0;yaw:0;vgx:0;vgy:0;vgz:0;templ:86;temph:88;tof:10;h:0;bat:87;baro:96.35;..."
        """
        try:
            # 末尾のセミコロンを除去して分割
            parts = state_str.strip(';').split(';')
            for part in parts:
                if ':' in part:
                    key, value = part.split(':')
                    
                    if key == 'bat':
                        self.state['bat'] = int(value)
                    elif key == 'h':
                        self.state['h'] = int(value)
                    elif key == 'temph':
                        self.state['temp'] = int(value)
            
            self.state['last_update'] = time.time()
            self.state['active'] = True
            
        except Exception:
            pass

    def send_command(self, command, timeout=7):
        """
        コマンドを送信し、応答を待機する

        Args:
            command: 送信するコマンド文字列
            timeout: タイムアウト時間（秒）

        Returns:
            bool: コマンドが正常に実行されたかどうか
        """
        self.response = None
        self.log({"level": "INFO", "message": f"[{self.name}] 送信: {command}"})
        
        try:
            self.socket.sendto(command.encode("utf-8"), self.tello_address)
        except Exception as e:
            self.log({"level": "ERROR", "message": f"[{self.name}] 送信エラー: {e}"})
            return False

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
        try:
            self.socket.close()
        except:
            pass
        try:
            self.state_socket.close()
        except:
            pass