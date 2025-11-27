"""
設定管理モジュール

アプリケーション全体で使用される定数と設定値を管理します。
"""

# フォント設定
FONT_NORMAL = ("Yu Gothic UI", 10)
FONT_BOLD_LARGE = ("Yu Gothic UI", 12, "bold")
FONT_HEADER = ("Yu Gothic UI", 10, "bold")
FONT_MONOSPACE = ("Consolas", 10)

# 色設定
COLOR_PRIMARY = "#0078D7"
COLOR_PRIMARY_HOVER = "#005f9e"
COLOR_PRIMARY_DISABLED = "#5a9fd4"
COLOR_ACCENT = "#0078D7"
COLOR_ACCENT_HOVER = "#005f9e"
COLOR_DANGER = "#d13438"
COLOR_DANGER_HOVER = "#a4262c"
COLOR_DANGER_DISABLED = "#e89c9f"
COLOR_SUCCESS = "#28a745"
COLOR_WARNING = "#ffc107"
COLOR_ERROR = "#dc3545"
COLOR_BACKGROUND = "#f0f0f0"
COLOR_TEXT = "#333"
COLOR_HIGHLIGHT = "#d0e9f8"

# ウィンドウ設定
WINDOW_TITLE = "Drone Show Controller for Tello Scratch"
WINDOW_SIZE = "1500x1200"
WINDOW_MIN_SIZE = (800, 600)
MAIN_PADDING = 15

# ドローン設定
DEFAULT_DRONE_PREFIX = "Tello_"
CONFIG_FILENAME = "tello_config.json"

# ファイル形式
SUPPORTED_PROJECT_FILES = [("Scratch プロジェクト", "*.sb3")]
SUPPORTED_AUDIO_FILES = [
    ("音楽ファイル", "*.mp3;*.wav;*.ogg;*.flac"),
    ("MP3ファイル", "*.mp3"),
    ("WAVファイル", "*.wav"),
    ("OGGファイル", "*.ogg"),
    ("FLACファイル", "*.flac"),
    ("すべてのファイル", "*.*"),
]

# UI更新間隔（ミリ秒）
LOG_QUEUE_UPDATE_INTERVAL = 200  # パフォーマンス最適化のため200msに設定

# ログレベル
LOG_LEVEL_INFO = "INFO"
LOG_LEVEL_SUCCESS = "SUCCESS"
LOG_LEVEL_WARNING = "WARNING"
LOG_LEVEL_ERROR = "ERROR"

# タイムラインイベントタイプ
EVENT_TYPE_TAKEOFF = "TAKEOFF"
EVENT_TYPE_COMMAND = "COMMAND"
EVENT_TYPE_WAIT = "WAIT"
EVENT_TYPE_WARNING = "WARNING"
EVENT_TYPE_LAND = "LAND"
EVENT_TYPE_INFO = "INFO"
