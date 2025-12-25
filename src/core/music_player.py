"""
音楽再生モジュール
"""

import threading
import time
import os
import sys
import contextlib

try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    import librosa
    import numpy as np

    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False


class MusicPlayer:
    """音楽再生を管理するクラス"""

    def __init__(self, log_queue=None):
        """
        音楽プレイヤーの初期化

        Args:
            log_queue: ログキュー（オプション）
        """
        self.log_queue = log_queue
        self.music_path = None
        self.music_list = []  # メドレー用の音楽リスト
        self.interval_seconds = 0.0  # 曲間のインターバル（秒）
        self.is_playing = False
        self.stop_event = threading.Event()
        self.pygame_available = PYGAME_AVAILABLE
        self._waveform_cache = {}  # 波形データのキャッシュ
        self._raw_waveform_cache = {}  # 生の波形データ（絶対値）のキャッシュ
        self._duration_cache = {}  # 音楽の長さのキャッシュ
        self._loading_waveforms = set()  # 現在ロード中のパス
        self._waveform_lock = threading.Lock()
        self._stderr_lock = threading.Lock()

        # pygameが利用可能な場合のみ初期化
        if self.pygame_available:
            try:
                # libmpg123の警告（ID3タグ関連）を抑制
                with self._suppress_stderr():
                    pygame.mixer.init()
                self._log("INFO", "音楽プレイヤーを初期化しました。")
            except Exception as e:
                self._log("ERROR", f"音楽プレイヤーの初期化に失敗: {e}")
                self.pygame_available = False
        else:
            self._log(
                "WARNING",
                "pygameがインストールされていません。音楽再生機能は使用できません。",
            )

    @contextlib.contextmanager
    def _suppress_stderr(self):
        """Cレベルのstderr出力を抑制するコンテキストマネージャ"""
        if os.name != "nt":
            yield
            return

        save_fd = None
        null_fd = None
        try:
            save_fd = os.dup(2)
            null_fd = os.open(os.devnull, os.O_RDWR)
            os.dup2(null_fd, 2)
            yield
        except Exception:
            # 例外が発生しても、finallyで復旧させるためにここでは何もしない
            # contextlibが例外を再送出する
            pass
        finally:
            if save_fd is not None:
                os.dup2(save_fd, 2)
                os.close(save_fd)
            if null_fd is not None:
                os.close(null_fd)

    def _log(self, level, message):
        """ログを出力"""
        if self.log_queue:
            self.log_queue.put({"level": level, "message": message})

    def set_music(self, music_path, show_log=True):
        """
        再生する音楽ファイルを設定（単一ファイル）

        Args:
            music_path: 音楽ファイルのパス
            show_log: ログを表示するかどうか
        """
        self.music_path = music_path
        if music_path and show_log:
            self._log("INFO", f"音楽ファイルを設定: {os.path.basename(music_path)}")

    def set_music_list(self, music_list):
        """
        メドレー再生用の音楽リストを設定

        Args:
            music_list: 音楽設定のリスト
                       [{"path": "...", "start": 0.0, "end": 120.0}, ...]
                       または互換性のためのパス文字列のリスト
        """
        if not music_list:
            self.music_list = []
            return

        # 互換性のために文字列リストを辞書リストに変換
        new_list = []
        for item in music_list:
            if isinstance(item, str):
                new_list.append({"path": item, "start": 0.0, "end": 0.0})
            else:
                new_list.append(item.copy())

        self.music_list = new_list
        if self.music_list:
            self._log("INFO", f"音楽リストを設定: {len(self.music_list)}曲")

    def get_music_list(self):
        """現在の音楽リストを取得"""
        return [item.copy() for item in self.music_list]

    def set_interval(self, seconds):
        """
        曲間のインターバルを設定

        Args:
            seconds: インターバル時間（秒）
        """
        self.interval_seconds = max(0.0, float(seconds))
        if self.interval_seconds > 0:
            self._log("INFO", f"曲間インターバルを設定: {self.interval_seconds}秒")

    def get_interval(self):
        """現在のインターバル設定を取得"""
        return self.interval_seconds

    def play(self, delay=0):
        """
        音楽を再生（単一ファイルまたはメドレー）

        Args:
            delay: 再生開始前の遅延時間（秒）
        """
        if not self.pygame_available:
            self._log("WARNING", "pygameが利用できないため、音楽を再生できません。")
            return

        # stop_eventをリセット
        self.stop_event.clear()

        # メドレーリストがある場合はメドレー再生
        if self.music_list:
            self._play_medley(delay)
        elif self.music_path:
            self._play_single(delay)
        else:
            self._log("WARNING", "音楽ファイルが設定されていません。")

    def _play_single(self, delay=0, start_time=0.0, end_time=0.0):
        """単一の音楽ファイルを再生"""
        # 停止イベントをクリア（直前のstopの影響を消す）
        self.stop_event.clear()

        def _play_thread():
            try:
                # 遅延
                if delay > 0:
                    self._log("INFO", f"{delay:.1f}秒後に音楽を再生します...")
                    # 遅延中も停止をチェック
                    start_wait = time.time()
                    while time.time() - start_wait < delay:
                        if self.stop_event.is_set():
                            return
                        time.sleep(0.1)

                if self.stop_event.is_set():
                    return

                # 音楽をロード
                try:
                    pygame.mixer.music.unload()
                    pygame.mixer.music.load(self.music_path)
                except Exception as e:
                    self._log("ERROR", f"音楽ファイルのロードに失敗: {e}")
                    return

                # 音量を確認
                if pygame.mixer.music.get_volume() <= 0.01:
                    pygame.mixer.music.set_volume(1.0)

                # 再生開始
                try:
                    if start_time > 0:
                        pygame.mixer.music.play(start=start_time)
                    else:
                        pygame.mixer.music.play()
                except Exception as e:
                    self._log("WARNING", f"開始位置の指定再生に失敗しました: {e}")
                    pygame.mixer.music.play()

                self.is_playing = True
                self._log(
                    "SUCCESS", f"🎵 音楽の再生を開始しました ({start_time:.1f}s～)"
                )

                # 再生開始を待機して確認
                time.sleep(0.3)

                # 再生が終了するか停止イベントがセットされるまで待機
                while pygame.mixer.music.get_busy() and not self.stop_event.is_set():
                    if end_time > 0:
                        current_pos = start_time + (
                            pygame.mixer.music.get_pos() / 1000.0
                        )
                        if current_pos >= end_time:
                            break
                    time.sleep(0.1)

                pygame.mixer.music.stop()
                self.is_playing = False
                if not self.stop_event.is_set():
                    self._log("INFO", "音楽の再生が終了しました。")

            except Exception as e:
                self._log("ERROR", f"音楽再生エラー: {e}")
                self.is_playing = False

        # 別スレッドで再生
        play_thread = threading.Thread(target=_play_thread)
        play_thread.daemon = True
        play_thread.start()

    def _play_medley(self, delay=0):
        """メドレー（複数の音楽）を再生"""
        # 停止イベントをクリア
        self.stop_event.clear()

        def _play_thread():
            try:
                # 遅延
                if delay > 0:
                    self._log("INFO", f"{delay:.1f}秒後にメドレーを再生します...")
                    # 遅延中も停止をチェック
                    start_wait = time.time()
                    while time.time() - start_wait < delay:
                        if self.stop_event.is_set():
                            return
                        time.sleep(0.1)

                if self.stop_event.is_set():
                    return

                self.is_playing = True
                self._log(
                    "SUCCESS", f"🎵 メドレー再生を開始（全{len(self.music_list)}曲）"
                )

                # インターバル設定を表示
                if self.interval_seconds > 0:
                    self._log("INFO", f"曲間インターバル: {self.interval_seconds}秒")

                # 各曲を順番に再生
                for i, music_config in enumerate(self.music_list, 1):
                    if self.stop_event.is_set():
                        break

                    music_path = music_config["path"]
                    start_time = music_config.get("start", 0.0)
                    end_time = music_config.get("end", 0.0)

                    # ファイル名を取得
                    filename = os.path.basename(music_path)

                    try:
                        # 音楽をロード
                        pygame.mixer.music.unload()
                        pygame.mixer.music.load(music_path)

                        # 音量を確認
                        if pygame.mixer.music.get_volume() <= 0.01:
                            pygame.mixer.music.set_volume(1.0)

                        # 再生開始
                        try:
                            if start_time > 0:
                                pygame.mixer.music.play(start=start_time)
                            else:
                                pygame.mixer.music.play()
                        except Exception as e:
                            self._log(
                                "WARNING", f"開始位置の指定再生に失敗しました: {e}"
                            )
                            pygame.mixer.music.play()

                        self._log(
                            "INFO",
                            f"♪ {i}/{len(self.music_list)}: {filename} ({start_time:.1f}s～)",
                        )

                        # 再生開始を待機して確認
                        time.sleep(0.3)

                        # 再生が終了するまで待機
                        while (
                            pygame.mixer.music.get_busy()
                            and not self.stop_event.is_set()
                        ):
                            if end_time > 0:
                                current_pos = start_time + (
                                    pygame.mixer.music.get_pos() / 1000.0
                                )
                                if current_pos >= end_time:
                                    break
                            time.sleep(0.1)

                        pygame.mixer.music.stop()

                        if self.stop_event.is_set():
                            break

                        # 曲間インターバル（最後の曲の後は不要）
                        if i < len(self.music_list) and self.interval_seconds > 0:
                            self._log(
                                "INFO",
                                f"⏱️ インターバル: {self.interval_seconds}秒待機中...",
                            )
                            # インターバル中も停止イベントをチェック
                            interval_start = time.time()
                            while (
                                time.time() - interval_start < self.interval_seconds
                                and not self.stop_event.is_set()
                            ):
                                time.sleep(0.1)

                            if self.stop_event.is_set():
                                break

                    except Exception as e:
                        self._log("ERROR", f"曲 {i} の再生エラー: {e}")
                        continue

                self.is_playing = False
                if not self.stop_event.is_set():
                    self._log("INFO", "メドレーの再生が終了しました。")

            except Exception as e:
                self._log("ERROR", f"メドレー再生エラー: {e}")
                self.is_playing = False

        # 別スレッドで再生
        play_thread = threading.Thread(target=_play_thread)
        play_thread.daemon = True
        play_thread.start()

    def stop(self):
        """音楽を停止"""
        if not self.pygame_available:
            return

        try:
            self.stop_event.set()
            if self.is_playing:
                pygame.mixer.music.stop()
                self.is_playing = False
                self._log("INFO", "音楽を停止しました。")
        except Exception as e:
            self._log("ERROR", f"音楽停止エラー: {e}")

    def pause(self):
        """音楽を一時停止"""
        if not self.pygame_available:
            return

        try:
            if self.is_playing:
                pygame.mixer.music.pause()
                self._log("INFO", "音楽を一時停止しました。")
        except Exception as e:
            self._log("ERROR", f"音楽一時停止エラー: {e}")

    def unpause(self):
        """音楽の一時停止を解除"""
        if not self.pygame_available:
            return

        try:
            pygame.mixer.music.unpause()
            self._log("INFO", "音楽の再生を再開しました。")
        except Exception as e:
            self._log("ERROR", f"音楽再開エラー: {e}")

    def get_volume(self):
        """現在の音量を取得（0.0〜1.0）"""
        if not self.pygame_available:
            return 0.0

        try:
            return pygame.mixer.music.get_volume()
        except:
            return 0.0

    def set_volume(self, volume):
        """
        音量を設定

        Args:
            volume: 音量（0.0〜1.0）
        """
        if not self.pygame_available:
            return

        try:
            volume = max(0.0, min(1.0, volume))  # 0.0〜1.0の範囲に制限
            pygame.mixer.music.set_volume(volume)
            self._log("INFO", f"音量を{int(volume * 100)}%に設定しました。")
        except Exception as e:
            self._log("ERROR", f"音量設定エラー: {e}")

    def get_music_duration(self, music_path, fallback_to_load=True):
        """
        音楽ファイルの長さを取得（秒）

        Args:
            music_path: 音楽ファイルのパス（または設定辞書）
            fallback_to_load: キャッシュにない場合にロードして取得するか
        Returns:
            float: 長さ（秒）。取得失敗時や未ロード時は0.0
        """
        # 辞書が渡された場合はpathを取り出す
        if isinstance(music_path, dict):
            music_path = music_path.get("path", "")

        if (
            not self.pygame_available
            or not music_path
            or not os.path.exists(music_path)
        ):
            return 0.0

        # キャッシュを確認
        if music_path in self._duration_cache:
            return self._duration_cache[music_path]

        if not fallback_to_load:
            return 0.0

        try:
            # pygame.mixer.Soundはファイルを全ロードするため重い
            # 可能であればメタデータから取得したいが、ここではキャッシュで対応
            sound = pygame.mixer.Sound(music_path)
            duration = sound.get_length()
            self._duration_cache[music_path] = duration
            return duration
        except Exception as e:
            # librosaで試行（pygameで失敗する場合のフォールバック）
            if LIBROSA_AVAILABLE:
                try:
                    duration = librosa.get_duration(path=music_path)
                    if duration > 0:
                        self._duration_cache[music_path] = duration
                        return duration
                except:
                    pass

            self._log(
                "ERROR", f"音楽の長さ取得に失敗 ({os.path.basename(music_path)}): {e}"
            )
            return 0.0

    def get_waveform(self, music_path, num_points=500):
        """
        音楽ファイルの波形データを取得（キャッシュ付き）

        Args:
            music_path: 音楽ファイルのパス（または設定辞書）
            num_points: 取得するポイント数
        Returns:
            list: 波形データのリスト（0.0〜1.0の範囲）。失敗時は空リスト
        """
        # 辞書が渡された場合はpathを取り出す
        if isinstance(music_path, dict):
            music_path = music_path.get("path", "")

        if not LIBROSA_AVAILABLE or not music_path or not os.path.exists(music_path):
            return []

        # キャッシュキー（パスとポイント数）
        cache_key = (music_path, num_points)
        if cache_key in self._waveform_cache:
            return self._waveform_cache[cache_key]

        try:
            # 生データのキャッシュを確認
            if music_path in self._raw_waveform_cache:
                y_abs = self._raw_waveform_cache[music_path]
                if y_abs is None:  # 過去に失敗したファイル
                    return []
            else:
                # ファイルサイズをチェック（200MB以上の場合は一旦スキップして安全を期す）
                try:
                    if os.path.getsize(music_path) > 200 * 1024 * 1024:
                        self._log(
                            "DEBUG",
                            "ファイルサイズが大きすぎるため波形取得をスキップします",
                        )
                        self._raw_waveform_cache[music_path] = None
                        return []
                except:
                    pass

                # サンプリングレートを大幅に下げてメモリ消費を抑える
                try:
                    # 非常に長いファイルの場合に備え、まず長さを確認
                    duration = self.get_music_duration(music_path)

                    # 30分以上のファイルは波形取得をスキップ（メモリ保護）
                    if duration > 1800:
                        self._log(
                            "DEBUG",
                            f"ファイルが長すぎるため波形取得をスキップします ({duration:.1f}s)",
                        )
                        self._raw_waveform_cache[music_path] = None
                        return []

                    # librosa.load で sr を指定
                    # 内部での巨大配列生成を避けるため、まず読み込みを試みる
                    y, sr = librosa.load(music_path, sr=500)
                except (
                    MemoryError,
                    ValueError,
                    RuntimeError,
                    np.core._exceptions._ArrayMemoryError,
                ) as e:
                    self._log("DEBUG", f"メモリ制限により波形取得をスキップします: {e}")
                    self._raw_waveform_cache[music_path] = None
                    return []
                except Exception as e:
                    self._log("DEBUG", f"波形ロード失敗: {e}")
                    self._raw_waveform_cache[music_path] = None
                    return []

                if len(y) > 0:
                    # 絶対値を取る
                    y_abs = np.abs(y)
                    self._raw_waveform_cache[music_path] = y_abs
                else:
                    self._raw_waveform_cache[music_path] = None
                    return []

            # num_pointsに分割して各区間の最大値を取得
            chunks = np.array_split(y_abs, num_points)
            waveform = [
                float(np.max(chunk)) if len(chunk) > 0 else 0.0 for chunk in chunks
            ]

            # 正規化（最大値を1.0にする）
            max_val = max(waveform) if waveform else 0
            if max_val > 0:
                waveform = [v / max_val for v in waveform]

            self._waveform_cache[cache_key] = waveform
            return waveform
        except Exception as e:
            self._log("DEBUG", f"波形処理エラー: {e}")
            self._waveform_cache[cache_key] = []  # 失敗をキャッシュして再試行を防ぐ

        return []

    def request_waveform(self, music_path, num_points=500, callback=None):
        """
        非同期で波形データをリクエストする

        Args:
            music_path: 音楽ファイルのパス（または設定辞書）
            num_points: ポイント数
            callback: 完了時に呼ばれる関数 callback(waveform)
        """
        # 辞書が渡された場合はpathを取り出す
        if isinstance(music_path, dict):
            music_path = music_path.get("path", "")

        # キャッシュにあれば即座にコールバック
        cache_key = (music_path, num_points)
        with self._waveform_lock:
            if cache_key in self._waveform_cache:
                if callback:
                    callback(self._waveform_cache[cache_key])
                return

            # すでにロード中なら何もしない（コールバックは最初のスレッドに任せるか、今回は簡易化）
            if music_path in self._loading_waveforms:
                return
            self._loading_waveforms.add(music_path)

        def _load_thread():
            try:
                waveform = self.get_waveform(music_path, num_points)
                if callback:
                    callback(waveform)
            finally:
                with self._waveform_lock:
                    if music_path in self._loading_waveforms:
                        self._loading_waveforms.remove(music_path)

        thread = threading.Thread(target=_load_thread, daemon=True)
        thread.start()


def is_pygame_available():
    """pygameが利用可能かどうかを返す"""
    return PYGAME_AVAILABLE
