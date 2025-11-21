"""
音楽再生モジュール
"""

import threading
import time

try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


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
        self.is_playing = False
        self.stop_event = threading.Event()
        self.pygame_available = PYGAME_AVAILABLE

        # pygameが利用可能な場合のみ初期化
        if self.pygame_available:
            try:
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

    def _log(self, level, message):
        """ログを出力"""
        if self.log_queue:
            self.log_queue.put({"level": level, "message": message})

    def set_music(self, music_path):
        """
        再生する音楽ファイルを設定（単一ファイル）

        Args:
            music_path: 音楽ファイルのパス
        """
        self.music_path = music_path
        if music_path:
            self._log("INFO", f"音楽ファイルを設定: {music_path}")

    def set_music_list(self, music_list):
        """
        メドレー再生用の音楽リストを設定

        Args:
            music_list: 音楽ファイルパスのリスト
        """
        self.music_list = music_list.copy() if music_list else []
        if self.music_list:
            self._log("INFO", f"音楽リストを設定: {len(self.music_list)}曲")

    def get_music_list(self):
        """現在の音楽リストを取得"""
        return self.music_list.copy()

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

    def _play_single(self, delay=0):
        """単一の音楽ファイルを再生"""

        def _play_thread():
            try:
                # 遅延
                if delay > 0:
                    self._log("INFO", f"{delay:.1f}秒後に音楽を再生します...")
                    time.sleep(delay)

                if self.stop_event.is_set():
                    return

                # 音楽をロードして再生
                pygame.mixer.music.load(self.music_path)
                pygame.mixer.music.play()
                self.is_playing = True
                self._log("SUCCESS", "🎵 音楽の再生を開始しました。")

                # 再生が終了するまで待機
                while pygame.mixer.music.get_busy() and not self.stop_event.is_set():
                    time.sleep(0.1)

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

        def _play_thread():
            try:
                # 遅延
                if delay > 0:
                    self._log("INFO", f"{delay:.1f}秒後にメドレーを再生します...")
                    time.sleep(delay)

                if self.stop_event.is_set():
                    return

                self.is_playing = True
                self._log(
                    "SUCCESS", f"🎵 メドレー再生を開始（全{len(self.music_list)}曲）"
                )

                # 各曲を順番に再生
                for i, music_path in enumerate(self.music_list, 1):
                    if self.stop_event.is_set():
                        break

                    # ファイル名を取得
                    import os

                    filename = os.path.basename(music_path)

                    try:
                        # 音楽をロードして再生
                        pygame.mixer.music.load(music_path)
                        pygame.mixer.music.play()
                        self._log("INFO", f"♪ {i}/{len(self.music_list)}: {filename}")

                        # 再生が終了するまで待機
                        while (
                            pygame.mixer.music.get_busy()
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


def is_pygame_available():
    """pygameが利用可能かどうかを返す"""
    return PYGAME_AVAILABLE
