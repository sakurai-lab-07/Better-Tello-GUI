"""
音楽プレイヤーモジュール

ドローンショーと同期して音楽を再生する機能を提供します。
pygameを使用して音楽ファイルの再生、停止、音量制御を行います。
"""

import threading
import time
import os
import tempfile
import hashlib
from pathlib import Path
from typing import Optional, List

try:
    import yt_dlp

    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


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
        self.music_list = []  # メドレー用の音楽リスト
        self.current_index = 0  # 現在再生中の曲のインデックス
        self.current_music = None  # 単一ファイル再生用
        self.interval_seconds = 0.0  # 曲間インターバル（秒）

        # YouTube音源のキャッシュディレクトリ
        self.temp_dir = Path(tempfile.gettempdir()) / "tello_youtube_cache"
        self.temp_dir.mkdir(exist_ok=True)

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
            audio_path: 音楽ファイルのパスまたはYouTube URL
            delay_seconds: 遅延時間（秒）
        """
        try:
            # 遅延待機
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            if self.stop_requested:
                return

            # YouTube URLの場合はキャッシュファイルを取得
            actual_path = audio_path
            if self._is_youtube_url(audio_path):
                if self.log_callback:
                    self.log_callback(
                        {
                            "level": "INFO",
                            "message": "YouTube音源を取得中...",
                        }
                    )
                actual_path = self._download_youtube_audio(audio_path)
                if not actual_path:
                    raise Exception("YouTube音源の取得に失敗しました")

            # 音楽ファイルを読み込んで再生
            self.pygame.mixer.music.load(actual_path)
            self.pygame.mixer.music.play()
            self.is_playing = True

            if self.log_callback:
                display_name = (
                    os.path.basename(actual_path)
                    if not self._is_youtube_url(audio_path)
                    else "YouTube"
                )
                self.log_callback(
                    {
                        "level": "INFO",
                        "message": f"♪ 音楽再生開始: {display_name}",
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

    def set_music_list(self, music_list: List[str]):
        """
        メドレー用の音楽リストを設定

        Args:
            music_list: 音楽ファイルパスのリスト
        """
        self.music_list = music_list.copy() if music_list else []
        self.current_index = 0

    def set_music(self, music_path: str):
        """
        単一の音楽ファイルを設定

        Args:
            music_path: 音楽ファイルのパス
        """
        self.current_music = music_path

    def get_music_list(self) -> list:
        """
        メドレー用の音楽リストを取得

        Returns:
            音楽ファイルパスのリスト
        """
        return self.music_list.copy() if self.music_list else []

    def get_interval(self) -> float:
        """
        曲間インターバルを取得

        Returns:
            インターバル秒数
        """
        return self.interval_seconds

    def set_interval(self, seconds: float):
        """
        曲間インターバルを設定

        Args:
            seconds: インターバル秒数（0.0以上）
        """
        self.interval_seconds = max(0.0, seconds)

    def play_medley(self, delay_seconds: float = 0.0):
        """
        メドレーを再生

        Args:
            delay_seconds: 再生開始までの遅延時間（秒）
        """
        if not self.available or not self.music_list:
            return

        if self.is_playing:
            self.stop()

        self.stop_requested = False
        self.current_index = 0
        self.play_thread = threading.Thread(
            target=self._play_medley, args=(delay_seconds,), daemon=True
        )
        self.play_thread.start()

    def _play_medley(self, delay_seconds: float):
        """
        メドレーを順番に再生する内部メソッド

        Args:
            delay_seconds: 最初の曲再生開始までの遅延時間（秒）
        """
        try:
            # 遅延待機
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            if self.stop_requested:
                return

            # 各曲を順番に再生
            for i, audio_path in enumerate(self.music_list):
                if self.stop_requested:
                    break

                self.current_index = i

                # 曲を読み込んで再生
                self.pygame.mixer.music.load(audio_path)
                self.pygame.mixer.music.play()
                self.is_playing = True

                filename = audio_path.split("/")[-1].split("\\")[-1]
                if self.log_callback:
                    self.log_callback(
                        {
                            "level": "INFO",
                            "message": f"♪ {i + 1}/{len(self.music_list)}: {filename}",
                        }
                    )

                # 再生終了まで待機
                while self.pygame.mixer.music.get_busy() and not self.stop_requested:
                    time.sleep(0.1)

                # インターバル待機（最後の曲の後は待機しない）
                if (
                    i < len(self.music_list) - 1
                    and self.interval_seconds > 0
                    and not self.stop_requested
                ):
                    if self.log_callback:
                        self.log_callback(
                            {
                                "level": "INFO",
                                "message": f"⏱️ インターバル: {self.interval_seconds}秒",
                            }
                        )
                    time.sleep(self.interval_seconds)

            self.is_playing = False

            if not self.stop_requested and self.log_callback:
                self.log_callback({"level": "INFO", "message": "♪ メドレー再生完了"})

        except Exception as e:
            self.is_playing = False
            if self.log_callback:
                self.log_callback(
                    {"level": "ERROR", "message": f"メドレー再生エラー: {e}"}
                )

    def _is_youtube_url(self, url: str) -> bool:
        """
        YouTube URLかどうかを判定

        Args:
            url: チェックするURL文字列

        Returns:
            bool: YouTube URLの場合True
        """
        if not url:
            return False
        return url.startswith(("http://", "https://")) and (
            "youtube.com" in url or "youtu.be" in url
        )

    def _download_youtube_audio(self, url: str) -> Optional[str]:
        """
        YouTube URLから音声をダウンロードしてキャッシュ

        Args:
            url: YouTube URL

        Returns:
            str: ダウンロードしたファイルのパス、失敗時はNone
        """
        if not YT_DLP_AVAILABLE:
            if self.log_callback:
                self.log_callback(
                    {
                        "level": "ERROR",
                        "message": "yt-dlpがインストールされていません",
                    }
                )
            return None

        try:
            # URLのMD5ハッシュをファイル名として使用
            url_hash = hashlib.md5(url.encode()).hexdigest()
            cache_file = self.temp_dir / f"{url_hash}.mp3"

            # キャッシュが存在すれば再利用
            if cache_file.exists():
                if self.log_callback:
                    self.log_callback(
                        {
                            "level": "INFO",
                            "message": "キャッシュから音源を読み込みました",
                        }
                    )
                return str(cache_file)

            # yt-dlpで音声をダウンロード
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": str(cache_file.with_suffix("")),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "quiet": True,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if cache_file.exists():
                if self.log_callback:
                    self.log_callback(
                        {
                            "level": "INFO",
                            "message": "YouTube音源をキャッシュしました",
                        }
                    )
                return str(cache_file)
            else:
                raise Exception("ダウンロードしたファイルが見つかりません")

        except Exception as e:
            if self.log_callback:
                self.log_callback(
                    {"level": "ERROR", "message": f"YouTube音源の取得に失敗: {e}"}
                )
            return None
