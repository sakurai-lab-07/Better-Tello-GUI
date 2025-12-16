import socket, threading, time

class TelloController:
    def __init__(self, pc_ip, name, port_offset, log_queue):
        self.name, self.log_queue = name, log_queue
        self.tello_addr = ("192.168.10.1", 8889)
        self.pc_ip = pc_ip

        # コマンドソケット
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((pc_ip, 9000 + port_offset))

        # ステータスソケット (8890)
        self.state_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.state_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: self.state_socket.bind((pc_ip, 8890))
        except: pass

        self.state = {"bat": 0, "h": 0, "active": False, "last_update": 0}
        self.response = None
        self.stop_evt = threading.Event()
        
        threading.Thread(target=self._recv_resp, daemon=True).start()
        threading.Thread(target=self._recv_state, daemon=True).start()

    def _recv_resp(self):
        while not self.stop_evt.is_set():
            try: data, _ = self.socket.recvfrom(1024); self.response = data.decode().strip()
            except: break

    def _recv_state(self):
        while not self.stop_evt.is_set():
            try:
                data, _ = self.state_socket.recvfrom(1024)
                for part in data.decode().strip(';').split(';'):
                    if ':' in part:
                        k, v = part.split(':')
                        if k == 'bat': self.state['bat'] = int(v)
                        if k == 'h': self.state['h'] = int(v)
                self.state['last_update'] = time.time()
                self.state['active'] = True
            except: break

    def get_state(self):
        if time.time() - self.state["last_update"] > 3.0: self.state["active"] = False
        return self.state

    def send_command(self, cmd, timeout=7):
        self.response = None
        try: self.socket.sendto(cmd.encode(), self.tello_addr)
        except: return False
        start = time.time()
        while self.response is None:
            if self.stop_evt.is_set() or (time.time() - start > timeout): return False
            time.sleep(0.1)
        return "ok" in self.response.lower() or cmd == "land"

    def close(self):
        self.stop_evt.set()
        self.socket.close(); self.state_socket.close()