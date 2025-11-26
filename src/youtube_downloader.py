"""
YouTube動画情報取得モジュール
YouTube URLから動画情報を取得する
"""

import re
from typing import Optional, Dict


class YouTubeDownloader:
    """YouTube URL処理クラス"""

    def __init__(self, log_queue=None):
        """
        YouTube Downloaderの初期化

        Args:
            log_queue: ログキュー（オプション）
        """
        self.log_queue = log_queue

    def _log(self, level: str, message: str):
        """ログを出力"""
        if self.log_queue:
            self.log_queue.put({"level": level, "message": message})

    def is_available(self) -> bool:
        """
        yt-dlpが利用可能かチェック

        Returns:
            bool: yt-dlpがインストールされている場合True
        """
        try:
            import yt_dlp

            return True
        except ImportError:
            return False

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """
        YouTube URLかどうかを判定

        Args:
            url: チェックするURL文字列

        Returns:
            bool: YouTube URLの場合True
        """
        if not url:
            return False

        youtube_patterns = [
            r"^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+",
            r"^https?://(?:www\.)?youtu\.be/[\w-]+",
            r"^https?://(?:www\.)?youtube\.com/embed/[\w-]+",
            r"^https?://(?:www\.)?youtube\.com/v/[\w-]+",
        ]

        return any(re.match(pattern, url.strip()) for pattern in youtube_patterns)

    def get_video_info(self, url: str) -> Optional[Dict[str, str]]:
        """
        YouTube動画の情報を取得

        Args:
            url: YouTube URL

        Returns:
            dict: 動画情報（title, duration等）、取得失敗時はNone
        """
        try:
            import yt_dlp

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration", 0),
                    "url": url,
                }

        except Exception as e:
            error_msg = f"YouTube動画情報の取得に失敗: {e}"
            self._log("ERROR", error_msg)
            print(error_msg)
            return None
