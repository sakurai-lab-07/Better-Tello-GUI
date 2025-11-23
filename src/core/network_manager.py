"""
ネットワーク管理モジュール
Windowsのnetshコマンドを使用してWi-Fiインターフェース情報を取得・制御します
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

    def get_connected_tellos(self):
        """現在TELLOに接続されているインターフェースとIPの一覧を取得する"""
        if not self.is_windows: return []
        
        tello_connections = []
        interfaces = self._get_wifi_interfaces()

        for iface in interfaces:
            # SSIDがTELLOで始まっているか (大文字小文字無視)
            if iface['ssid'].upper().startswith("TELLO-"):
                ip = self._get_interface_ip(iface['name'])
                if ip:
                    tello_connections.append({
                        'interface': iface['name'],
                        'ssid': iface['ssid'],
                        'ip': ip
                    })
        return tello_connections

    def connect_all_tellos(self, log_callback=None):
        """
        利用可能なWi-Fiインターフェースを使って、周囲のTelloに片っ端から接続する
        Returns:
            list: 接続に成功したSSIDのリスト
        """
        if not self.is_windows: return []

        # 1. 利用可能なWi-Fiインターフェースを取得 (例: Wi-Fi 1, Wi-Fi 2...)
        interfaces = self._get_wifi_interfaces()
        # 接続されていない、またはTello以外に繋がっているインターフェースを優先的に使う
        available_ifaces = [iface['name'] for iface in interfaces]
        
        if not available_ifaces:
            if log_callback: log_callback("エラー: Wi-Fiインターフェースが見つかりません。")
            return []

        # 2. 周囲のTELLO-XXXXネットワークをスキャン
        if log_callback: log_callback("周囲のネットワークをスキャン中...")
        found_tellos = self._scan_tello_networks()
        
        if not found_tellos:
            if log_callback: log_callback("TELLOネットワークが見つかりませんでした。")
            return []
        
        if log_callback: log_callback(f"検出されたTello: {len(found_tellos)}機 ({', '.join(found_tellos)})")

        connected_ssids = []

        # 3. マッチングして接続 (インターフェース数かTello数の少ない方に合わせる)
        count = min(len(available_ifaces), len(found_tellos))
        
        for i in range(count):
            iface_name = available_ifaces[i]
            target_ssid = found_tellos[i]
            
            if log_callback: log_callback(f"接続試行: {iface_name} -> {target_ssid}")
            
            # プロファイル作成と接続
            if self._connect_interface_to_ssid(iface_name, target_ssid):
                connected_ssids.append(target_ssid)
                if log_callback: log_callback(f"成功: {iface_name} に {target_ssid} を接続しました。")
            else:
                if log_callback: log_callback(f"失敗: {iface_name} -> {target_ssid}")

        # DHCPでIPが振られるのを少し待つ必要があるかもしれないので、呼び出し元で待機推奨
        return connected_ssids

    def _get_wifi_interfaces(self):
        """netshコマンドですべてのWi-Fiインターフェースの状態を取得"""
        try:
            output = subprocess.check_output("netsh wlan show interfaces", shell=True).decode('cp932', errors='ignore')
            interfaces = []
            current_iface = {}
            
            for line in output.split('\n'):
                line = line.strip()
                if not line: continue
                
                if line.startswith("名前") or line.startswith("Name"):
                    if current_iface: interfaces.append(current_iface)
                    try:
                        iface_name = line.split(':', 1)[1].strip()
                        current_iface = {'name': iface_name, 'ssid': ''}
                    except IndexError: continue
                
                elif line.startswith("SSID"):
                    try:
                        ssid_val = line.split(':', 1)[1].strip()
                        if current_iface: current_iface['ssid'] = ssid_val
                    except IndexError: continue
            
            if current_iface: interfaces.append(current_iface)
            return interfaces
        except Exception as e:
            print(f"Interface scan error: {e}")
            return []

    def _get_interface_ip(self, interface_name):
        """指定されたインターフェース名のIPアドレス(IPv4)を取得"""
        try:
            cmd = f'netsh interface ip show config name="{interface_name}"'
            output = subprocess.check_output(cmd, shell=True).decode('cp932', errors='ignore')
            ip_pattern = re.search(r'(IP アドレス|IP Address).+?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', output)
            if ip_pattern: return ip_pattern.group(2)
            return None
        except Exception: return None

    def _scan_tello_networks(self):
        """周囲のTELLO-から始まるSSIDを一意のリストとして取得"""
        try:
            # ネットワーク一覧を取得
            output = subprocess.check_output("netsh wlan show networks mode=bssid", shell=True).decode('cp932', errors='ignore')
            tello_ssids = set()
            
            for line in output.split('\n'):
                line = line.strip()
                # "SSID 1 : TELLO-C65210" のような形式
                if line.startswith("SSID") and "TELLO-" in line.upper():
                    try:
                        ssid = line.split(':', 1)[1].strip()
                        if ssid: tello_ssids.add(ssid)
                    except: continue
            
            return sorted(list(tello_ssids))
        except Exception:
            return []

    def _connect_interface_to_ssid(self, interface_name, ssid):
        """指定インターフェースで指定SSIDに接続（プロファイルが無ければ作成）"""
        try:
            # 1. プロファイルが存在するか確認する代わりに、念の為毎回プロファイルを作成・上書き登録する
            # TelloはOpenネットワークなのでテンプレートから作成可能
            xml_content = self._create_open_profile_xml(ssid)
            
            # 一時ファイルとしてXMLを保存
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as temp_xml:
                temp_xml.write(xml_content)
                temp_xml_path = temp_xml.name

            # 2. プロファイルをシステムに追加
            # netsh wlan add profile filename="x.xml" interface="Wi-Fi"
            add_cmd = f'netsh wlan add profile filename="{temp_xml_path}" interface="{interface_name}"'
            subprocess.run(add_cmd, shell=True, check=True, stdout=subprocess.DEVNULL)
            
            # 一時ファイル削除
            try: os.remove(temp_xml_path)
            except: pass

            # 3. 接続実行
            # netsh wlan connect name="TELLO-XXXX" interface="Wi-Fi"
            connect_cmd = f'netsh wlan connect name="{ssid}" interface="{interface_name}"'
            subprocess.run(connect_cmd, shell=True, check=True, stdout=subprocess.DEVNULL)
            
            # 接続完了まで少し待機（非同期なのでコマンド成功＝接続完了ではないが、キックは成功）
            time.sleep(2) 
            return True

        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def _create_open_profile_xml(self, ssid):
        """Windows Wi-Fiプロファイル(Open/No Auth)のXML文字列を生成"""
        # hexコードへの変換が必要な場合があるが、ASCII範囲ならそのままnameでいけることが多い
        # 念のためhexも用意するのが確実だが、Telloはシンプルなのでこれで試す
        xml = f"""<?xml version="1.0"?>
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
        return xml