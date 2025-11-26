import time
import socket
import threading


class TelloController:
    def __init__(self, pc_ip, name, port_offset, log_queue):
        self.name = name
        self.log_queue = log_queue
        self.tello_address = ("192.168.10.1", 8889)
        self.pc_address = (pc_ip, 9000 + port_offset)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(self.pc_address)
        self.response = None
        self.stop_event = threading.Event()
        self.response_thread = threading.Thread(target=self._receive_response)
        self.response_thread.daemon = True
        self.response_thread.start()

    def log(self, log_item):
        self.log_queue.put(log_item)

    def _receive_response(self):
        while not self.stop_event.is_set():
            try:
                data, _ = self.socket.recvfrom(1024)
                self.response = data.decode("utf-8").strip()
            except Exception:
                break

    def send_command(self, command, timeout=7):
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
        if "ok" in self.response or command.startswith("land"):
            self.log({"level": "SUCCESS", "message": f"[{self.name}] 応答: OK"})
            return True
        else:
            self.log(
                {"level": "WARNING", "message": f"[{self.name}] 応答: {self.response}"}
            )
            return False

    def close(self):
        self.stop_event.set()
        self.socket.close()
        self.response_thread.join(timeout=1)
