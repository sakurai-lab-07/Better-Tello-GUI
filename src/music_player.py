"""
音楽プレイヤーモジュール

ドローンショーと同期して音楽を再生する機能を提供します。
pygameを使用して音楽ファイルの再生、停止、音量制御を行います。
"""

import threading
import time
from typing import Optional


class MusicPlayer:
    """
    音楽再生を管理するクラス

    pygameを使用して音楽ファイルを再生します。
    pygameが利用できない場合はエラーメッセージを表示します。
    """

    def __init__(self, log_callback=None):
        """
        音楽プレイヤーを初期化

        Args:
            log_callback: ログメッセージを出力するコールバック関数
        """
        self.log_callback = log_callback
        self.is_playing = False
        self.play_thread = None
        self.stop_requested = False

        try:
            import pygame

            pygame.mixer.init()
            self.pygame = pygame
            self.available = True
        except ImportError:
            self.available = False
            if self.log_callback:
                self.log_callback(
                    {
                        "level": "WARNING",
                        "message": "pygame がインストールされていないため、音楽再生機能は利用できません。",
                    }
                )

    def play(self, audio_path: str, delay_seconds: float = 0.0):
        """
        音楽ファイルを再生

        Args:
            audio_path: 音楽ファイルのパス
            delay_seconds: 再生開始までの遅延時間（秒）
        """
        if not self.available or not audio_path:
            return

        if self.is_playing:
            self.stop()

        self.stop_requested = False
        self.play_thread = threading.Thread(
            target=self._play_with_delay, args=(audio_path, delay_seconds), daemon=True
        )
        self.play_thread.start()

    def _play_with_delay(self, audio_path: str, delay_seconds: float):
        """
        遅延後に音楽を再生する内部メソッド

        Args:
            audio_path: 音楽ファイルのパス
            delay_seconds: 遅延時間（秒）
        """
        try:
            # 遅延待機
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            if self.stop_requested:
                return

            # 音楽ファイルを読み込んで再生
            self.pygame.mixer.music.load(audio_path)
            self.pygame.mixer.music.play()
            self.is_playing = True

            if self.log_callback:
                self.log_callback(
                    {
                        "level": "INFO",
                        "message": f"♪ 音楽再生開始: {audio_path.split('/')[-1]}",
                    }
                )

            # 再生終了まで待機
            while self.pygame.mixer.music.get_busy() and not self.stop_requested:
                time.sleep(0.1)

            self.is_playing = False

            if not self.stop_requested and self.log_callback:
                self.log_callback({"level": "INFO", "message": "♪ 音楽再生完了"})

        except Exception as e:
            self.is_playing = False
            if self.log_callback:
                self.log_callback({"level": "ERROR", "message": f"音楽再生エラー: {e}"})

    def stop(self):
        """音楽再生を停止"""
        if not self.available:
            return

        self.stop_requested = True

        try:
            if self.pygame.mixer.music.get_busy():
                self.pygame.mixer.music.stop()
            self.is_playing = False

            if self.log_callback:
                self.log_callback({"level": "INFO", "message": "♪ 音楽を停止しました"})
        except Exception as e:
            if self.log_callback:
                self.log_callback({"level": "ERROR", "message": f"音楽停止エラー: {e}"})

    def pause(self):
        """音楽を一時停止"""
        if not self.available or not self.is_playing:
            return

        try:
            self.pygame.mixer.music.pause()
        except Exception as e:
            if self.log_callback:
                self.log_callback(
                    {"level": "ERROR", "message": f"音楽一時停止エラー: {e}"}
                )

    def unpause(self):
        """一時停止を解除"""
        if not self.available:
            return

        try:
            self.pygame.mixer.music.unpause()
        except Exception as e:
            if self.log_callback:
                self.log_callback({"level": "ERROR", "message": f"音楽再開エラー: {e}"})

    def set_volume(self, volume: float):
        """
        音量を設定

        Args:
            volume: 音量（0.0 ～ 1.0）
        """
        if not self.available:
            return

        try:
            volume = max(0.0, min(1.0, volume))  # 0.0～1.0の範囲に制限
            self.pygame.mixer.music.set_volume(volume)
        except Exception as e:
            if self.log_callback:
                self.log_callback({"level": "ERROR", "message": f"音量設定エラー: {e}"})
