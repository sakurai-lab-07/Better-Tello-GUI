"""
ネットワーク管理モジュール (安全版)
PC内蔵Wi-Fiの誤爆防止機能付き
"""
import subprocess
import re
import platform
import os
import time
import tempfile

class NetworkManager:
    def __init__(self):
        self.is_windows = platform.system() == "Windows"

    def _run_command(self, cmd):
        """コマンド実行（文字化け対策済み）"""
        try:
            raw_output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
            for enc in ['cp932', 'utf-8', 'shift_jis', 'mbcs']:
                try: return raw_output.decode(enc).strip()
                except: continue
            return raw_output.decode('cp932', errors='ignore').strip()
        except subprocess.CalledProcessError:
            return ""

    def get_wifi_interfaces_list(self):
        """Wi-Fiインターフェース名のリストを返す"""
        interfaces = self._get_wifi_interfaces()
        return [i['name'] for i in interfaces]

    # --- ★全自動セットアップ用：IP固定化 ---
    def set_static_ip(self, interface_name, ip_address):
        """指定したインターフェースを固定IPにする（管理者権限必須）"""
        if not self.is_windows: return False
        
        # ゲートウェイは設定しない（インターネット不要なため）
        cmd = f'netsh interface ip set address "{interface_name}" static {ip_address} 255.255.255.0'
        self._run_command(cmd)
        
        # 反映確認
        check_ip = self._get_interface_ip(interface_name)
        return check_ip == ip_address

    # --- ★Wi-Fi接続用：Tello接続（誤爆防止フィルタ付き） ---
    def connect_all_tellos(self, log_callback=None):
        """
        全アダプタで周囲のTelloに接続
        【安全機能】IPが '192.168.10.x' に設定されているアダプタだけを使用する
        """
        if not self.is_windows: return []
        
        # 1. 全インターフェースを取得
        interfaces = self._get_wifi_interfaces()
        if not interfaces:
            if log_callback: log_callback("エラー: Wi-Fiアダプタなし")
            return []

        # 2. Tello用アダプタだけを選別（フィルタリング）
        target_ifaces = []
        for iface in interfaces:
            name = iface['name']
            current_ip = self._get_interface_ip(name)
            
            # IPが '192.168.10.' で始まるものだけを「Tello用」と認定
            if current_ip and current_ip.startswith("192.168.10."):
                target_ifaces.append(name)
            else:
                # 家のWi-Fiなどはここに来るので無視される
                pass

        if not target_ifaces:
            if log_callback: log_callback("Tello用に設定されたアダプタが見つかりません。\n先に「セットアップ」を行ってください。")
            return []

        if log_callback: log_callback(f"Tello用アダプタ({len(target_ifaces)}個)を使用してスキャン中...")

        # 3. 周囲のTelloを探す
        found_ssids = self._scan_tello_networks()
        if not found_ssids:
            if log_callback: log_callback("Telloが見つかりません")
            return []

        connected_ssids = []
        count = min(len(target_ifaces), len(found_ssids))

        # 4. 接続実行
        for i in range(count):
            iface_name = target_ifaces[i]
            ssid = found_ssids[i]
            
            if log_callback: log_callback(f"接続試行: {iface_name} -> {ssid}")
            if self._connect_to_ssid(iface_name, ssid):
                connected_ssids.append(ssid)
        
        return connected_ssids

    # --- 内部メソッド ---
    def _get_wifi_interfaces(self):
        output = self._run_command("netsh wlan show interfaces")
        interfaces = []
        sections = re.split(r'\n\s*\n', output)
        for section in sections:
            name_match = re.search(r'(?:名前|Name)\s*:\s*(.*)', section)
            ssid_match = re.search(r'SSID\s*:\s*(.*)', section)
            if name_match:
                interfaces.append({
                    'name': name_match.group(1).strip(),
                    'ssid': ssid_match.group(1).strip() if ssid_match else ""
                })
        return interfaces

    def _get_interface_ip(self, name):
        output = self._run_command(f'netsh interface ip show config name="{name}"')
        match = re.search(r'IP.*:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', output)
        return match.group(1) if match else None

    def _scan_tello_networks(self):
        output = self._run_command("netsh wlan show networks")
        found = re.findall(r'SSID\s*\d*\s*:\s*(TELLO-[\w\d]+)', output, re.IGNORECASE)
        return sorted(list(set(found)))

    def _connect_to_ssid(self, iface, ssid):
        try:
            xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
<name>{ssid}</name><SSIDConfig><SSID><name>{ssid}</name></SSIDConfig></SSIDConfig>
<connectionType>ESS</connectionType><connectionMode>auto</connectionMode>
<MSM><security><authEncryption><authentication>open</authentication><encryption>none</encryption>
<useOneX>false</useOneX></authEncryption></security></MSM></WLANProfile>"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
                f.write(xml)
                path = f.name
            subprocess.run(f'netsh wlan add profile filename="{path}" interface="{iface}"', shell=True, capture_output=True)
            os.remove(path)
            subprocess.run(f'netsh wlan connect name="{ssid}" interface="{iface}"', shell=True, capture_output=True)
            return True
        except: return False