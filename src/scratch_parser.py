"""
Scratchプロジェクト解析モジュール
"""

import zipfile
import json
import math
from config import (
    SCRATCH_TO_CM_RATE,
    MIN_TELLO_MOVE,
    INITIAL_HOVER_HEIGHT_CM,
    TELLO_HORIZONTAL_SPEED_CMS,
    TELLO_VERTICAL_SPEED_CMS,
)


class ScratchProjectParser:
    """Scratchプロジェクトファイル(.sb3)を解析してTelloコマンドのスケジュールを生成"""

    def __init__(self, sb3_path, log_queue):
        """
        パーサーの初期化

        Args:
            sb3_path: Scratchプロジェクトファイル(.sb3)のパス
            log_queue: ログキュー
        """
        self.sb3_path = sb3_path
        self.log_queue = log_queue
        self.project_data = self._load_project_data()
        self.has_any_valid_action = False

    def log(self, message, level="INFO"):
        """ログをキューに追加"""
        self.log_queue.put({"level": level, "message": message})

    def _load_project_data(self):
        """Scratchプロジェクトファイルからproject.jsonを読み込む"""
        try:
            with zipfile.ZipFile(self.sb3_path, "r") as z:
                with z.open("project.json") as f:
                    return json.load(f)
        except Exception as e:
            self.log(
                f"エラー: {self.sb3_path} の読み込みまたは解析に失敗しました。 -> {e}",
                level="ERROR",
            )
            return None

    def _get_input_value(self, block_input, blocks):
        """
        ブロックの入力値を取得

        Args:
            block_input: ブロックの入力データ
            blocks: 全ブロックの辞書

        Returns:
            float or None: 入力値（取得できない場合はNone）
        """
        if not block_input:
            return None

        # 直接値が指定されている場合
        if block_input[0] == 1 and isinstance(block_input[1], list):
            return float(block_input[1][1])

        # 他のブロックを参照している場合
        elif block_input[0] == 1 and isinstance(block_input[1], str):
            ref_block = blocks.get(block_input[1])
            if ref_block and ref_block["opcode"] == "math_number":
                return float(ref_block["fields"]["NUM"][0])

        return None

    def _parse_sprite_to_actions(self, sprite_name, blocks):
        """スプライトのブロックをアクションシーケンスに変換"""
        action_sequence = []
        start_block_id = self._find_start_block(blocks)

        if not start_block_id:
            return []

        self.has_any_valid_action = True

        # 初期位置の設定
        pos_x, pos_y = 0, 0
        pos_z = INITIAL_HOVER_HEIGHT_CM

        # ブロックを順番に処理
        block_id = start_block_id
        while block_id:
            block = blocks.get(block_id)
            if not block:
                break

            opcode = block.get("opcode")
            inputs = block.get("inputs", {})

            # アクション情報の初期化
            action = {
                "duration": 0.0,
                "commands": [],
                "warnings": [],
                "is_wait": False,
                "sprite_name": sprite_name,
            }

            # オペコードごとの処理
            if opcode == "motion_gotoxy":
                # x,y座標への移動
                val_x = self._get_input_value(inputs.get("X"), blocks)
                val_y = self._get_input_value(inputs.get("Y"), blocks)
                if val_x is not None and val_y is not None:
                    action["commands"], action["duration"], action["warnings"] = (
                        self._pos_to_commands(sprite_name, pos_x, pos_y, val_x, val_y)
                    )
                    pos_x, pos_y = val_x, val_y

            elif opcode == "motion_movesteps":
                # 指定歩数の移動
                steps = self._get_input_value(inputs.get("STEPS"), blocks)
                if steps is not None:
                    rad = math.radians(90 - 90)
                    new_x = pos_x + steps * math.sin(rad)
                    new_y = pos_y + steps * math.cos(rad)
                    action["commands"], action["duration"], action["warnings"] = (
                        self._pos_to_commands(sprite_name, pos_x, pos_y, new_x, new_y)
                    )
                    pos_x, pos_y = new_x, new_y

            elif opcode == "control_wait":
                # 待機
                duration = self._get_input_value(inputs.get("DURATION"), blocks)
                if duration is not None:
                    action["duration"] = duration
                    action["is_wait"] = True

            elif opcode == "looks_setsizeto":
                # 大きさの設定（高度）
                size = self._get_input_value(inputs.get("SIZE"), blocks)
                if size is not None:
                    action["commands"], action["duration"], action["warnings"] = (
                        self._height_to_commands(sprite_name, pos_z, size)
                    )
                    pos_z = size

            elif opcode == "looks_changesizeby":
                # 大きさの変更（高度変化）
                change = self._get_input_value(inputs.get("CHANGE"), blocks)
                if change is not None:
                    new_z = pos_z + change
                    action["commands"], action["duration"], action["warnings"] = (
                        self._height_to_commands(sprite_name, pos_z, new_z)
                    )
                    pos_z = new_z

            elif (
                opcode == "control_stop"
                and block.get("fields", {}).get("STOP_OPTION", [None])[0] == "all"
            ):
                # すべてを止める
                action["commands"].append({"target": "system", "command": "stop_all"})

            action_sequence.append(action)
            block_id = block.get("next")

        return action_sequence

    def parse_to_schedule(self):
        """プロジェクトデータから実行スケジュールを生成"""
        if not self.project_data:
            return [], 0.0

        # 各スプライトのアクションを解析
        all_actions = {}
        for target in self.project_data.get("targets", []):
            if target.get("isStage", False):
                continue

            sprite_name = target.get("name")
            blocks = target.get("blocks", {})
            all_actions[sprite_name] = self._parse_sprite_to_actions(
                sprite_name, blocks
            )

        # タイムラインの構築
        final_event_list = []
        master_time = 0.0

        while any(all_actions.values()):
            max_duration_this_step = 0.0
            actions_this_step = []

            # 各スプライトから次のアクションを取得
            for sprite_name, action_list in all_actions.items():
                if action_list:
                    action = action_list.pop(0)
                    actions_this_step.append(action)
                    max_duration_this_step = max(
                        max_duration_this_step, action["duration"]
                    )

            # アクションをイベントリストに変換
            for action in actions_this_step:
                # 待機時間の警告
                if action["is_wait"] and action["duration"] < max_duration_this_step:
                    msg = (
                        f"[{action['sprite_name']}] 待機時間({action['duration']:.2f}秒)が"
                        f"ステップ最長動作({max_duration_this_step:.2f}秒)より短いため、待機が延長されます。"
                    )
                    final_event_list.append(
                        {"time": master_time, "type": "WARNING", "text": msg}
                    )

                # 待機イベントの追加
                if action["is_wait"]:
                    final_event_list.append(
                        {
                            "time": master_time,
                            "type": "WAIT",
                            "target": action["sprite_name"],
                            "text": f"{action['duration']:.2f}秒 待機",
                        }
                    )

                # コマンドイベントの追加
                for cmd in action["commands"]:
                    cmd["time"] = master_time
                    cmd["type"] = "COMMAND"
                    final_event_list.append(cmd)

                # 警告メッセージの追加
                for warning_msg in action["warnings"]:
                    final_event_list.append(
                        {"time": master_time, "type": "WARNING", "text": warning_msg}
                    )

            master_time += max_duration_this_step

        # 時間順にソート（警告を先に表示）
        final_event_list.sort(
            key=lambda x: (x["time"], 0 if x["type"] == "WARNING" else 1)
        )
        return final_event_list, master_time

    def _find_start_block(self, blocks):
        """「緑の旗が押されたとき」ブロックを探す"""
        for block_id, block in blocks.items():
            if block.get("opcode") == "event_whenflagclicked":
                return block.get("next")
        return None

    def _pos_to_commands(self, name, x1, y1, x2, y2):
        """位置の変化をTelloコマンドに変換"""
        cmds = []
        warnings = []

        # 移動量の計算
        dx = int((x2 - x1) * SCRATCH_TO_CM_RATE)
        dy = int((y2 - y1) * SCRATCH_TO_CM_RATE)
        duration = 0.0

        # 最小移動量のチェック
        if 0 < abs(dx) < MIN_TELLO_MOVE:
            warnings.append(
                f"[{name}] 水平移動 {abs(dx)}cmは小さすぎるため無視されました。(最小{MIN_TELLO_MOVE}cm)"
            )
        if 0 < abs(dy) < MIN_TELLO_MOVE:
            warnings.append(
                f"[{name}] 前後移動 {abs(dy)}cmは小さすぎるため無視されました。(最小{MIN_TELLO_MOVE}cm)"
            )

        # 水平移動コマンドの生成
        if abs(dx) >= MIN_TELLO_MOVE:
            direction = "right" if dx > 0 else "left"
            cmds.append({"target": name, "command": f"{direction} {abs(dx)}"})
            duration = max(duration, abs(dx) / TELLO_HORIZONTAL_SPEED_CMS)

        # 前後移動コマンドの生成
        if abs(dy) >= MIN_TELLO_MOVE:
            direction = "forward" if dy > 0 else "back"
            cmds.append({"target": name, "command": f"{direction} {abs(dy)}"})
            duration = max(duration, abs(dy) / TELLO_HORIZONTAL_SPEED_CMS)

        return cmds, duration, warnings

    def _height_to_commands(self, name, z1, z2):
        """高度の変化をTelloコマンドに変換"""
        cmds = []
        warnings = []

        # 高度変化量の計算
        dz = int(z2 - z1)
        duration = 0.0

        # 最小移動量のチェック
        if 0 < abs(dz) < MIN_TELLO_MOVE:
            warnings.append(
                f"[{name}] 高さ変更 {abs(dz)}cmは小さすぎるため無視されました。(最小{MIN_TELLO_MOVE}cm)"
            )

        # 上下移動コマンドの生成
        if abs(dz) >= MIN_TELLO_MOVE:
            direction = "up" if dz > 0 else "down"
            cmds.append({"target": name, "command": f"{direction} {abs(dz)}"})
            duration = max(duration, abs(dz) / TELLO_VERTICAL_SPEED_CMS)

        return cmds, duration, warnings
