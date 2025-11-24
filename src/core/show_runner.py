"""
ドローンショー実行モジュール
"""

import time
import threading
import traceback
# coreパッケージの中から読み込むように修正
from core.tello_controller import TelloController


class ShowRunner:
    """ドローンショー実行クラス"""

    def __init__(
        self,
        drones_config,
        schedule,
        stop_event,
        log_queue,
        total_time,
        controllers=None,
    ):
        """
        ShowRunnerの初期化

        Args:
            drones_config: ドローン設定のリスト（接続時に使用）
            schedule: 実行スケジュール
            stop_event: 停止イベント
            log_queue: ログキュー
            total_time: ショーの総実行時間
            controllers: 既存のコントローラー辞書（省略可）
        """
        self.drones_config = drones_config
        self.schedule = schedule
        self.stop_event = stop_event
        self.log_queue = log_queue
        self.total_time = total_time
        self.controllers = controllers if controllers is not None else {}

    def log(self, log_item):
        """ログをキューに追加"""
        self.log_queue.put(log_item)

    def connect(self):
        """ドローンに接続"""
        try:
            self.log(
                {"level": "INFO", "message": "--- ドローンへの接続を開始します... ---"}
            )

            # スケジュールに含まれるドローンを特定
            drone_names = set(
                evt["target"]
                for evt in self.schedule
                if evt.get("type") in ["COMMAND", "WAIT", "LAND"]
            )
            drones_to_init = [c for c in self.drones_config if c["name"] in drone_names]

            if not drones_to_init:
                self.log(
                    {
                        "level": "WARNING",
                        "message": "タイムラインに登場するドローンが設定されていません。",
                    }
                )
                self.log({"type": "connection_fail"})
                return

            threads, temp_controllers = [], {}
            for i, config in enumerate(drones_to_init):
                controller = TelloController(
                    config["pc_ip"], config["name"], i, self.log_queue
                )
                temp_controllers[config["name"]] = controller
                threads.append(
                    threading.Thread(target=controller.send_command, args=("command",))
                )

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            if all(
                c.response and "ok" in c.response for c in temp_controllers.values()
            ):
                self.log(
                    {"type": "connection_success", "controllers": temp_controllers}
                )
            else:
                self.log(
                    {
                        "level": "ERROR",
                        "message": "いくつかのドローンとの接続に失敗しました。IPアドレスを確認してください。",
                    }
                )
                self.log({"type": "connection_fail"})
                for c in temp_controllers.values():
                    c.close()
        except Exception as e:
            self.log({"level": "ERROR", "message": f"接続中にエラーが発生: {e}"})
            self.log({"type": "connection_fail"})

    def run_show(self):
        """ドローンショーを実行"""
        try:
            # UIのハイライトをクリア
            self.log({"type": "clear_highlight"})

            # 初期コマンドの実行（command, takeoff）
            _execute_initial_commands(self.controllers, self.stop_event, self.log_queue)

            if self.stop_event.is_set():
                raise threading.ThreadError("離陸中に停止イベントが発生しました。")

            # スケジュールの実行
            _execute_schedule(
                self.controllers,
                self.schedule,
                self.stop_event,
                self.log_queue,
                self.total_time,
            )

        except Exception as e:
            self.log(
                {
                    "level": "ERROR",
                    "message": f"\n--- 実行中にエラーが発生しました: {e} ---",
                }
            )
            self.log({"level": "ERROR", "message": traceback.format_exc()})

        finally:
            # クリーンアップ処理
            _cleanup_controllers(self.controllers, self.log_queue)


def run_show_worker(drones_config, schedule, stop_event, log_queue, total_time):
    """
    ドローンショーを実行するワーカー関数（別スレッドで実行）

    Args:
        drones_config: ドローン設定のリスト
        schedule: 実行スケジュール
        stop_event: 停止イベント
        log_queue: ログキュー
        total_time: ショーの総実行時間
    """
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

        # スケジュールに含まれるドローンを特定（LANDイベントも含める）
        drone_names_in_schedule = set(
            evt["target"]
            for evt in schedule
            if evt.get("type") in ["COMMAND", "WAIT", "LAND"]
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
        _execute_initial_commands(controllers, stop_event, log_queue)

        if stop_event.is_set():
            raise threading.ThreadError("離陸中に停止イベントが発生しました。")

        # スケジュールの実行
        _execute_schedule(controllers, schedule, stop_event, log_queue, total_time)

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
        _cleanup_controllers(controllers, log_queue)


def _execute_initial_commands(controllers, stop_event, log_queue):
    """初期コマンド（command, takeoff）を実行"""
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


def _execute_schedule(controllers, schedule, stop_event, log_queue, total_time):
    """スケジュールに従ってコマンドを実行"""
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

        # この時刻に実行するイベントを処理
        if not _process_events(controllers, schedule, exec_time, stop_event, log_queue):
            break

    # 最終待機時間
    _wait_for_completion(start_time, total_time, stop_event, log_queue)


def _process_events(controllers, schedule, exec_time, stop_event, log_queue):
    """指定時刻のイベントを処理

    Returns:
        bool: 続行する場合True、停止する場合False
    """
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
                return False

            target = cmd["target"]
            command = cmd["command"]

            if target in controllers:
                thread = threading.Thread(
                    target=controllers[target].send_command, args=(command,)
                )
                threads.append(thread)

        elif event["type"] == "LAND":
            # スケジュールされた着陸イベントの処理
            cmd = event
            command = cmd.get("command", "land")
            target_text = cmd.get("text", "")
            log_queue.put(
                {
                    "level": "INFO",
                    "message": f"--- スケジュールされた着陸を実行 ---",
                }
            )
            for c_name, c_controller in controllers.items():
                if c_name in target_text:  # テキストに対象ドローン名が含まれていれば
                    thread = threading.Thread(
                        target=c_controller.send_command, args=(command,)
                    )
                    threads.append(thread)

    # コマンド送信スレッドを一斉に開始
    for t in threads:
        t.start()

    return True


def _wait_for_completion(start_time, total_time, stop_event, log_queue):
    """ショー完了まで待機"""
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


def _cleanup_controllers(controllers, log_queue):
    """全ドローンを着陸させ、接続をクローズ"""
    log_queue.put({"type": "clear_highlight"})
    log_queue.put(
        {"level": "INFO", "message": "\n--- 全てのドローンを着陸させています... ---"}
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

    # ショー完了を通知
    log_queue.put({"type": "show_complete"})
