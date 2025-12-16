"""
設定と定数
"""

# -----------------------------------------------------------------------------
# アプリケーション設定
# -----------------------------------------------------------------------------
CONFIG_FILE = "tello_config.json"

# -----------------------------------------------------------------------------
# Tello設定
# -----------------------------------------------------------------------------
# Scratch座標からTello座標への変換レート
SCRATCH_TO_CM_RATE = 1

# Telloの最小移動距離（cm）
MIN_TELLO_MOVE = 20

# 初期ホバリング高度（cm）
INITIAL_HOVER_HEIGHT_CM = 80

# Telloの移動速度（cm/秒）
TELLO_HORIZONTAL_SPEED_CMS = 50.0
TELLO_VERTICAL_SPEED_CMS = 40.0

# Telloのネットワーク設定
TELLO_IP = "192.168.10.1"
TELLO_PORT = 8889
PC_PORT_BASE = 9000

# -----------------------------------------------------------------------------
# GUIスタイル設定
# -----------------------------------------------------------------------------
FONT_NORMAL = ("Yu Gothic UI", 10)
FONT_BOLD_LARGE = ("Yu Gothic UI", 12, "bold")
FONT_HEADER = ("Yu Gothic UI", 10, "bold")
FONT_MONOSPACE = ("Consolas", 10)

# 色設定
COLOR_BACKGROUND = "#f0f0f0"
COLOR_ACCENT = "#0078D7"
COLOR_ACCENT_HOVER = "#005f9e"
COLOR_STOP = "#d13438"
COLOR_STOP_HOVER = "#a4262c"
COLOR_SUCCESS = "#28a745"
COLOR_WARNING = "#ffc107"
COLOR_ERROR = "#dc3545"
COLOR_HIGHLIGHT = "#d0e9f8"
