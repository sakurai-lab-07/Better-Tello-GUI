"""
プロジェクト管理モジュール
.sb3ファイル、タイムライン情報、音楽設定などをまとめて保存・読み込み
"""

import json
import os
import shutil
import base64
from datetime import datetime
from pathlib import Path


class ProjectManager:
    """プロジェクトファイルの保存・読み込みを管理"""

    PROJECT_VERSION = "1.0"
    PROJECT_EXTENSION = ".telloproject"

    def __init__(self, log_queue=None):
        """
        プロジェクトマネージャーの初期化

        Args:
            log_queue: ログキュー（オプション）
        """
        self.log_queue = log_queue

    def _log(self, level, message):
        """ログを出力"""
        if self.log_queue:
            self.log_queue.put({"level": level, "message": message})

    def save_project(
        self,
        project_path,
        sb3_path=None,
        schedule=None,
        total_time=0.0,
        time_to_line_map=None,
        music_list=None,
        music_interval=0.0,
        drone_config=None,
        youtube_titles=None,
    ):
        """
        プロジェクトを保存

        Args:
            project_path: 保存先のプロジェクトファイルパス
            sb3_path: Scratchプロジェクトファイルのパス
            schedule: 解析されたタイムラインスケジュール
            total_time: 総実行時間
            time_to_line_map: 時間→行番号のマッピング
            music_list: 音楽ファイルのリスト
            music_interval: 曲間インターバル（秒）
            drone_config: ドローン設定情報
            youtube_titles: YouTube URLとタイトルの辞書

        Returns:
            bool: 保存が成功したかどうか
        """
        try:
            project_data = {
                "version": self.PROJECT_VERSION,
                "created_at": datetime.now().isoformat(),
                "sb3_file": None,
                "sb3_filename": None,
                "schedule": schedule,
                "total_time": total_time,
                "time_to_line_map": time_to_line_map or {},
                "music": {"list": [], "interval": music_interval},
                "drone_config": drone_config or {},
            }

            # .sb3ファイルを埋め込み（Base64エンコード）
            if sb3_path and os.path.exists(sb3_path):
                with open(sb3_path, "rb") as f:
                    sb3_data = f.read()
                    project_data["sb3_file"] = base64.b64encode(sb3_data).decode(
                        "utf-8"
                    )
                    project_data["sb3_filename"] = os.path.basename(sb3_path)
                    self._log("INFO", f".sb3ファイルを埋め込みました: {sb3_path}")

            # 音楽ファイルを埋め込み(Base64エンコード)またはYouTube URLを保存
            if music_list:
                for music_path in music_list:
                    # YouTube URLかどうかをチェック
                    if music_path.startswith(("http://", "https://")):
                        # YouTube URLはそのまま保存（タイトルも保存）
                        music_entry = {
                            "type": "url",
                            "url": music_path,
                        }
                        # タイトルがあれば保存
                        if youtube_titles and music_path in youtube_titles:
                            music_entry["title"] = youtube_titles[music_path]
                        project_data["music"]["list"].append(music_entry)
                        self._log("INFO", f"YouTube URLを保存しました: {music_path}")
                    elif os.path.exists(music_path):
                        # ローカルファイルはBase64エンコードして埋め込み
                        with open(music_path, "rb") as f:
                            music_data = f.read()
                            project_data["music"]["list"].append(
                                {
                                    "type": "file",
                                    "filename": os.path.basename(music_path),
                                    "data": base64.b64encode(music_data).decode(
                                        "utf-8"
                                    ),
                                }
                            )
                        self._log("INFO", f"音楽ファイルを埋め込みました: {music_path}")

            # プロジェクトファイルを保存
            with open(project_path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)

            self._log("INFO", f"プロジェクトを保存しました: {project_path}")
            return True

        except Exception as e:
            self._log("ERROR", f"プロジェクトの保存に失敗しました: {e}")
            return False

    def load_project(self, project_path):
        """
        プロジェクトを読み込み

        Args:
            project_path: 読み込むプロジェクトファイルのパス

        Returns:
            dict: プロジェクトデータ、または失敗時はNone
                {
                    'sb3_path': 一時的に展開された.sb3ファイルのパス,
                    'schedule': タイムラインスケジュール,
                    'total_time': 総実行時間,
                    'time_to_line_map': 時間→行番号のマッピング,
                    'music_paths': 音楽ファイルパスのリスト,
                    'music_interval': 曲間インターバル,
                    'drone_config': ドローン設定,
                }
        """
        try:
            with open(project_path, "r", encoding="utf-8") as f:
                project_data = json.load(f)

            # バージョンチェック
            version = project_data.get("version", "1.0")
            if version != self.PROJECT_VERSION:
                self._log(
                    "WARNING",
                    f"プロジェクトバージョンが異なります: {version} (現在: {self.PROJECT_VERSION})",
                )

            result = {
                "sb3_path": None,
                "schedule": project_data.get("schedule"),
                "total_time": project_data.get("total_time", 0.0),
                "time_to_line_map": project_data.get("time_to_line_map", {}),
                "music_paths": [],
                "music_interval": project_data.get("music", {}).get("interval", 0.0),
                "drone_config": project_data.get("drone_config", {}),
                "youtube_titles": {},
            }

            # 一時ディレクトリの作成
            temp_dir = Path(project_path).parent / ".tello_temp"
            temp_dir.mkdir(exist_ok=True)

            # .sb3ファイルを復元
            if project_data.get("sb3_file"):
                sb3_filename = project_data.get("sb3_filename", "project.sb3")
                sb3_temp_path = temp_dir / sb3_filename
                sb3_data = base64.b64decode(project_data["sb3_file"])
                with open(sb3_temp_path, "wb") as f:
                    f.write(sb3_data)
                result["sb3_path"] = str(sb3_temp_path)
                self._log("INFO", f".sb3ファイルを復元しました: {sb3_temp_path}")

            # 音楽ファイル/URLを復元
            music_list = project_data.get("music", {}).get("list", [])
            for music_item in music_list:
                item_type = music_item.get(
                    "type", "file"
                )  # 旧形式対応のため既定値はfile

                if item_type == "url":
                    # YouTube URLはそのまま追加
                    url = music_item.get("url")
                    if url:
                        result["music_paths"].append(url)
                        # タイトルがあれば復元
                        title = music_item.get("title")
                        if title:
                            result["youtube_titles"][url] = title
                        self._log("INFO", f"YouTube URLを読み込みました: {url}")
                else:
                    # ローカルファイルを復元
                    music_filename = music_item.get("filename")
                    music_data_b64 = music_item.get("data")
                    if music_filename and music_data_b64:
                        music_temp_path = temp_dir / music_filename
                        music_data = base64.b64decode(music_data_b64)
                        with open(music_temp_path, "wb") as f:
                            f.write(music_data)
                        result["music_paths"].append(str(music_temp_path))
                        self._log(
                            "INFO", f"音楽ファイルを復元しました: {music_temp_path}"
                        )

            self._log("INFO", f"プロジェクトを読み込みました: {project_path}")
            return result

        except Exception as e:
            self._log("ERROR", f"プロジェクトの読み込みに失敗しました: {e}")
            return None

    def cleanup_temp_files(self, project_path):
        """
        一時ファイルをクリーンアップ

        Args:
            project_path: プロジェクトファイルのパス
        """
        try:
            temp_dir = Path(project_path).parent / ".tello_temp"
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                self._log("INFO", "一時ファイルをクリーンアップしました")
        except Exception as e:
            self._log("WARNING", f"一時ファイルのクリーンアップに失敗: {e}")
