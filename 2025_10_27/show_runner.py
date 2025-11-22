import threading
import time
import traceback
import pygame # ★★★★★ pygameをインポート ★★★★★
import sys
from tello_controller import TelloController

class ShowRunner:
    def __init__(self, drones_config, schedule, stop_event, log_queue, total_time, controllers=None, audio_path=None):
        self.drones_config = drones_config; self.schedule = schedule; self.stop_event = stop_event
        self.log_queue = log_queue; self.total_time = total_time
        self.controllers = controllers if controllers is not None else {}
        self.audio_path = audio_path # ★★★★★ 音声ファイルのパスを受け取る ★★★★★

    def log(self, log_item): self.log_queue.put(log_item)

    def connect(self):
        try:
            self.log({"level": "INFO", "message": "--- ドローンへの接続を開始します... ---"})
            drone_names = set(evt['target'] for evt in self.schedule if evt.get('type') in ['COMMAND', 'WAIT', 'LAND']) # ★★★ LAND も対象に含める ★★★
            drones_to_init = [c for c in self.drones_config if c['name'] in drone_names]
            if not drones_to_init:
                 self.log({"level": "WARNING", "message": "タイムラインに登場するドローンが設定されていません。"}); self.log({"type": "connection_fail"}); return

            threads, temp_controllers = [], {}
            for i, config in enumerate(drones_to_init):
                controller = TelloController(config['pc_ip'], config['name'], i, self.log_queue)
                temp_controllers[config['name']] = controller
                threads.append(threading.Thread(target=controller.send_command, args=("command",)))
            
            for t in threads: t.start()
            for t in threads: t.join()

            if all(c.response and 'ok' in c.response for c in temp_controllers.values()):
                self.log({"type": "connection_success", "controllers": temp_controllers})
            else:
                self.log({"level": "ERROR", "message": "いくつかのドローンとの接続に失敗しました。IPアドレスを確認してください。"}); self.log({"type": "connection_fail"})
                for c in temp_controllers.values(): c.close()
        except Exception as e:
            self.log({"level": "ERROR", "message": f"接続中にエラーが発生: {e}"}); self.log({"type": "connection_fail"})

    def run_show(self):
        try:
            # ★★★★★ 音楽の準備 ★★★★★
            if self.audio_path:
                try:
                    pygame.mixer.init()
                    pygame.mixer.music.load(self.audio_path)
                except Exception as e:
                    self.log({"level": "ERROR", "message": f"音声ファイルの読み込みエラー: {e}"})
                    self.audio_path = None # エラーが発生した場合は再生しない
            
            self.log({"type": "clear_highlight"})
            all_event_times = sorted(list(set(evt['time'] for evt in self.schedule)))
            
            if 0.0 in all_event_times: self.log({"type": "highlight", "time": 0.0}); self._takeoff_sequence()
            
            start_time = time.time() 

            for i, exec_time in enumerate(all_event_times):
                if exec_time == 0.0: continue
                if self.stop_event.is_set(): break
                target_time = start_time + (exec_time - 8.0) 
                wait_time = target_time - time.time()
                if wait_time > 0: time.sleep(wait_time)
                if self.stop_event.is_set(): break

                self.log({"type": "highlight", "time": exec_time})
                self.log({"level": "INFO", "message": f"\n--- ステップ開始 ( {exec_time:.2f}秒地点 ) ---"})
                
                threads = []
                events_to_run = [evt for evt in self.schedule if evt.get('time') == exec_time]
                for event in events_to_run:
                    if event['type'] == 'WAIT': self.log({"level": "INFO", "message": f"--- {event['target']} | {event['text']} ---"})
                    elif event['type'] == 'COMMAND':
                        cmd = event
                        if cmd.get('command') == 'stop_all': self.log({"level": "INFO", "message": "--- Scratchからの「すべてを止める」命令を検知しました。 ---"}); self.stop_event.set(); break
                        target, command = cmd['target'], cmd['command']
                        if target in self.controllers: threads.append(threading.Thread(target=self.controllers[target].send_command, args=(command,)))
                    
                    # ★★★ 修正点: LAND イベントの処理を追加 ★★★
                    elif event['type'] == 'LAND':
                        cmd = event
                        command = cmd.get('command') # 'land'
                        target_text = cmd.get('text', '') # "着陸 (対象: Tello_A, Tello_B)"
                        self.log({"level": "INFO", "message": f"--- スケジュールされた着陸を実行 ---"})
                        for c_name, c_controller in self.controllers.items():
                            if c_name in target_text: # テキストに対象ドローン名が含まれていれば
                                threads.append(threading.Thread(target=c_controller.send_command, args=(command,)))

                if self.stop_event.is_set(): break
                for t in threads: t.start()
            
            final_wait_time = (start_time + (self.total_time - 8.0)) - time.time()
            if final_wait_time > 0 and not self.stop_event.is_set():
                self.log({"level": "INFO", "message": f"\n--- 最終ステップの動作完了を待機中... ({final_wait_time:.2f}秒) ---"}); time.sleep(final_wait_time)
            
            if not self.stop_event.is_set(): self.log({"level": "INFO", "message": "\n--- ショーが完了しました。 ---"})
        except Exception as e:
            self.log({"level": "ERROR", "message": f"\n--- 実行中にエラーが発生しました: {e} ---"}); self.log({"level": "ERROR", "message": traceback.format_exc()})
        finally:
            self._land_sequence()

    def _takeoff_sequence(self):
        if self.stop_event.is_set(): return
        self.log({"level": "INFO", "message": "\n--- 離陸シーケンスを開始 ---"})
        
        # ★★★★★ 音楽再生を開始 ★★★★★
        if self.audio_path:
            pygame.mixer.music.play()
            self.log({"level": "INFO", "message": "--- 音楽の再生を開始しました ---"})

        threads = [threading.Thread(target=c.send_command, args=('takeoff', 15)) for c in self.controllers.values()]
        for t in threads: t.start()
        for t in threads: t.join()

    def _land_sequence(self):
        # ★★★★★ 音楽を停止 ★★★★★
        if 'pygame' in sys.modules and pygame.mixer.get_init():
            pygame.mixer.music.stop()
            self.log({"level": "INFO", "message": "--- 音楽の再生を停止しました ---"})

        self.log({"type": "clear_highlight"})
        self.log({"level": "INFO", "message": "\n--- 全てのドローンを着陸させています... ---"})
        controllers_to_land = self.controllers or {}
        threads = [threading.Thread(target=c.send_command, args=('land', 5)) for c in controllers_to_land.values()]
        for t in threads: t.start()
        for t in threads: t.join()
        for c in controllers_to_land.values(): c.close()
        self.log({"level": "INFO", "message": "--- 全ての接続を閉じました。 ---"}); self.log({"type": "show_finished"})