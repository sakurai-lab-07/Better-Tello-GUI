"""
ネットワーク管理モジュール
Windowsのnetshコマンドを使用してWi-Fiインターフェース情報を取得・制御します
（文字化け対策・強力スキャン・デバッグ表示機能付き）
"""
import subprocess
import re
import platform
import os
import time
import tempfile
import sys

class NetworkManager:
    def __init__(self):
        self.is_windows = platform.system() == "Windows"

    def get_connected_tellos(self):
        """現在TELLOに接続されているインターフェースとIPの一覧を取得"""
        if not self.is_windows: return []
        
        tello_connections = []
        interfaces = self._get_wifi_interfaces()

        for iface in interfaces:
            ssid = iface.get('ssid', '')
            if ssid and ssid.upper().startswith("TELLO-"):
                ip = self._get_interface_ip(iface['name'])
                if ip:
                    tello_connections.append({
                        'interface': iface['name'],
                        'ssid': ssid,
                        'ip': ip
                    })
        return tello_connections

    def connect_all_tellos(self, log_callback=None):
        """利用可能なWi-Fiインターフェースを使って、周囲のTelloに接続する"""
        if not self.is_windows:
            if log_callback: log_callback("エラー: Windows専用機能です。")
            return []

        # 1. インターフェース取得
        interfaces = self._get_wifi_interfaces()
        if not interfaces:
            if log_callback: log_callback("エラー: Wi-Fiインターフェースが見つかりません。\n(コンソールのデバッグ出力を確認してください)")
            return []

        available_ifaces = [iface['name'] for iface in interfaces]
        
        # 2. スキャン (リトライ機能付き)
        if log_callback: log_callback("周囲のネットワークをスキャン中... (最大10秒)")
        found_tellos = self._scan_tello_networks_robust()
        
        if not found_tellos:
            if log_callback: log_callback("TELLOネットワークが見つかりませんでした。\n・Telloの電源が入って黄色点滅していますか？")
            return []
        
        if log_callback: log_callback(f"検出: {len(found_tellos)}機 ({', '.join(found_tellos)})")

        # 3. 接続
        connected_ssids = []
        count = min(len(available_ifaces), len(found_tellos))
        
        for i in range(count):
            iface_name = available_ifaces[i]
            target_ssid = found_tellos[i]
            
            if log_callback: log_callback(f"接続試行: {iface_name} -> {target_ssid}")
            
            if self._connect_interface_to_ssid(iface_name, target_ssid):
                connected_ssids.append(target_ssid)
                if log_callback: log_callback(f"コマンド送信成功: {iface_name} -> {target_ssid}")
            else:
                if log_callback: log_callback(f"コマンド送信失敗: {iface_name} -> {target_ssid}")

        # 4. 待機
        if connected_ssids:
            if log_callback: log_callback("接続の確立を待機しています... (IP取得待ち)")
            for i in range(15):
                time.sleep(1)
                current = self.get_connected_tellos()
                if len(current) >= len(connected_ssids):
                    if log_callback: log_callback(f"接続完了確認: {len(current)}台がネットワークに参加しました。")
                    break
            
        return connected_ssids

    def _run_command(self, cmd):
        """コマンドを実行して適切なエンコーディングでデコードする"""
        try:
            # rawバイト列を取得
            raw_output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
            
            # 順番にデコードを試す
            encodings = ['cp932', 'utf-8', 'shift_jis', 'mbcs']
            for enc in encodings:
                try:
                    return raw_output.decode(enc).strip()
                except UnicodeDecodeError:
                    continue
            
            # どうしてもダメな場合
            return raw_output.decode('cp932', errors='ignore').strip()
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {cmd}\nError: {e}")
            return ""
        except Exception as e:
            print(f"Execution error: {e}")
            return ""

    def _get_wifi_interfaces(self):
        """Wi-Fiインターフェース情報を取得"""
        output = self._run_command("netsh wlan show interfaces")
        
        interfaces = []
        current_iface = {}
        
        # デバッグ用: 出力が空ならコンソールに表示
        if not output:
            print("DEBUG: 'netsh wlan show interfaces' returned empty.")
            return []

        lines = output.split('\n')
        print(f"DEBUG: Found {len(lines)} lines in interface info.") # デバッグ表示

        for line in lines:
            line = line.strip()
            if not line: continue
            
            # "名前" "Name" などを柔軟に検知
            # 行に " : " が含まれていれば Key : Value とみなす
            if " : " in line:
                key, value = line.split(" : ", 1)
                key = key.strip()
                value = value.strip()
                
                # インターフェース名の検出 ("名前" or "Name")
                if "名前" in key or "Name" in key:
                    if current_iface: interfaces.append(current_iface)
                    current_iface = {'name': value, 'ssid': ''}
                    print(f"DEBUG: Found interface -> {value}") # デバッグ表示
                
                # SSIDの検出
                elif "SSID" in key and "BSSID" not in key:
                    if current_iface: current_iface['ssid'] = value
        
        if current_iface: interfaces.append(current_iface)
        
        if not interfaces:
            print("DEBUG: Failed to parse interfaces. Raw output below:")
            print("-" * 20)
            print(output)
            print("-" * 20)
            
        return interfaces

    def _get_interface_ip(self, interface_name):
        """IPアドレスを取得"""
        cmd = f'netsh interface ip show config name="{interface_name}"'
        output = self._run_command(cmd)
        
        # "IP アドレス" "IP Address" などを柔軟に検索
        # 正規表現: "IP" の後に何らかの文字があって " : " が来て、数値とドットが続く
        match = re.search(r'IP.*:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', output)
        if match:
            return match.group(1)
        return None

    def _scan_tello_networks_robust(self):
        """TELLOネットワークをスキャン"""
        tello_ssids = set()
        RETRY_COUNT = 3
        
        for i in range(RETRY_COUNT):
            output = self._run_command("netsh wlan show networks")
            
            for line in output.split('\n'):
                line = line.strip()
                if "TELLO-" in line.upper():
                    parts = line.split(':')
                    if len(parts) > 1:
                        ssid = parts[-1].strip()
                        if ssid.upper().startswith("TELLO-"):
                            tello_ssids.add(ssid)
            
            if tello_ssids: # 見つかったら終了せず、念のため蓄積する
                pass
                
            if i < RETRY_COUNT - 1:
                time.sleep(3)
        
        return sorted(list(tello_ssids))

    def _connect_interface_to_ssid(self, interface_name, ssid):
        """接続処理"""
        try:
            xml = self._create_open_profile_xml(ssid)
            # エンコーディングを指定してファイル作成
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as temp_xml:
                temp_xml.write(xml)
                temp_xml_path = temp_xml.name

            add_cmd = f'netsh wlan add profile filename="{temp_xml_path}" interface="{interface_name}"'
            subprocess.run(add_cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            try: os.remove(temp_xml_path)
            except: pass

            connect_cmd = f'netsh wlan connect name="{ssid}" interface="{interface_name}"'
            subprocess.run(connect_cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def _create_open_profile_xml(self, ssid):
        return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
	<name>{ssid}</name>
	<SSIDConfig>
		<SSID>
			<name>{ssid}</name>
		</SSID>
	</SSIDConfig>
	<connectionType>ESS</connectionType>
	<connectionMode>auto</connectionMode>
	<MSM>
		<security>
			<authEncryption>
				<authentication>open</authentication>
				<encryption>none</encryption>
				<useOneX>false</useOneX>
			</authEncryption>
		</security>
	</MSM>
</WLANProfile>"""