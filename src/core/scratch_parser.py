import zipfile
import json
import math


class ScratchProjectParser:
    def __init__(self, sb3_path, log_queue):
        self.TAKEOFF_DURATION = 8.0
        self.MIN_TELLO_MOVE = 20
        self.SCRATCH_TO_CM_RATE = 1
        self.INITIAL_HOVER_HEIGHT_CM = 80
        self.TELLO_HORIZONTAL_SPEED_CMS = 50.0
        self.TELLO_VERTICAL_SPEED_CMS = 40.0
        self.MOVE_TIME_OVERHEAD = 0.75
        self.MINIMUM_MOVE_TIME = 1.5
        self.sb3_path = sb3_path
        self.log_queue = log_queue
        self.project_data = self._load_project_data()
        self.has_any_valid_action = False

    def log(self, message, level="INFO"):
        self.log_queue.put({"level": level, "message": message})

    def log_parse(self, message, level="INFO"):
        """Push a parse-specific log entry so the GUI can route it to
        the 解析ログ pane."""
        self.log_queue.put({"type": "parse_log", "level": level, "message": message})

    def _describe_command(self, cmd):
        """Generate a short Japanese description for a command dict."""
        if not isinstance(cmd, dict):
            return str(cmd)
        if "action" in cmd:
            a = cmd.get("action")
            p = cmd.get("parameters", {}) or {}
            if a == "move_by":
                return f"相対移動: dx={p.get('dx', 0)} dy={p.get('dy', 0)}"
            if a == "move_to_local":
                return f"局所移動: lx={p.get('lx', 0)} ly={p.get('ly', 0)}"
            if a == "turn_right":
                return f"右回転: {p.get('degrees',0)}度"
            if a == "turn_left":
                return f"左回転: {p.get('degrees',0)}度"
            if a == "change_size_by":
                return f"サイズ変化: Δ={p.get('change',0)}"
            if a == "set_size_to":
                return f"サイズ設定: {p.get('size',0)}"
            if a == "set_stage_size":
                return f"ステージサイズ変更: {p.get('width',0)}x{p.get('height',0)}"
            return a
        if "command" in cmd:
            return cmd.get("command")
        return str(cmd)

    def _load_project_data(self):
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

    def _get_input_value(self, block_input, blocks, variable_state, custom_block_args):
        if not block_input:
            return 0.0
        input_type, input_value = block_input[0], block_input[1]

        if input_type in [1, 2]:
            if isinstance(input_value, list):
                try:
                    return float(input_value[1])
                except (ValueError, TypeError):
                    return 0.0
            if isinstance(input_value, str):
                ref_block = blocks.get(input_value)
                if not isinstance(ref_block, dict):
                    return 0.0

                opcode = ref_block.get("opcode", "")
                if opcode == "argument_reporter_string_number":
                    arg_name = ref_block["fields"]["VALUE"][0]
                    return custom_block_args.get(arg_name, 0.0)

                if opcode == "math_number":
                    try:
                        return float(ref_block["fields"]["NUM"][0])
                    except (ValueError, TypeError):
                        return 0.0

        elif input_type == 3 and isinstance(input_value, list) and input_value[0] == 12:
            var_id = input_value[2]
            return variable_state.get(var_id, 0.0)

        return 0.0

    def _get_broadcast_message(self, block_input, blocks):
        if not block_input:
            return ""
        if block_input[0] == 1 and isinstance(block_input[1], str):
            ref_block = blocks.get(block_input[1])
            if (
                isinstance(ref_block, dict)
                and ref_block.get("opcode") == "event_broadcast_menu"
            ):
                return ref_block["fields"]["BROADCAST_OPTION"][0]
        return ""

    def _canonical_preview_opcode(self, opcode):
        """Normalize opcode names so TurboWarp extension prefixes are removed
        and extension block names map to preview_* handlers.
        Returns a canonical opcode (possibly starting with 'preview_') or the
        original opcode if no mapping applies.
        """
        if not opcode or not isinstance(opcode, str):
            return opcode

        # If opcode already a preview_* handler, return as-is
        if opcode.startswith("preview_"):
            return opcode

        # Remove common TurboWarp/extension prefixes like "extName_..."
        parts = opcode.split("_")
        if len(parts) > 1:
            # If the leftmost part looks like an extension name listed in project
            exts = self.project_data.get("extensions", []) if self.project_data else []
            if parts[0] in exts:
                opcode = "_".join(parts[1:])

        # Also handle possible names that use camelCase or other styles by
        # mapping a few known extension block names to the preview_ form.
        known_preview_basenames = [
            "setStageSize",
            "setOriginHere",
            "setOriginXY",
            "clearOrigin",
            "turnRight",
            "turnLeft",
            "moveBy",
            "moveXBy",
            "moveYBy",
            "moveToLocal",
            "changeSizeBy",
            "setSizeTo",
            "getStageWidth",
            "getStageHeight",
            "getX",
            "getY",
            "getLocalX",
            "getLocalY",
        ]

        # If opcode exactly matches a known base name, produce preview_ form
        if opcode in known_preview_basenames:
            return f"preview_{opcode}"

        # If opcode contains one of the known basenames as suffix, map it too
        for base in known_preview_basenames:
            if opcode.endswith(base):
                return f"preview_{base}"

        # No mapping found: return original opcode
        return opcode

    def _find_procedure_definitions_for_target(self, target_blocks, all_blocks):
        procedures = {}
        for block_id, block in target_blocks.items():
            # ★★★★★ ここがエラーの原因でした！安全チェックを追加 ★★★★★
            # blockが辞書(ブロック情報)でない場合(リストなど)はスキップ
            if not isinstance(block, dict):
                continue

            if block.get("opcode") == "procedures_definition":
                prototype_id = block.get("inputs", {}).get(
                    "custom_block", [None, None]
                )[1]
                if prototype_id and prototype_id in all_blocks:
                    prototype_block = all_blocks[prototype_id]
                    mutation = prototype_block.get("mutation", {})
                    proccode = mutation.get("proccode")
                    if proccode:
                        arg_ids = json.loads(mutation.get("argumentids", "[]"))
                        arg_names = json.loads(mutation.get("argumentnames", "[]"))

                        procedures[proccode] = {
                            "start_block_id": block.get("next"),
                            "arg_ids": arg_ids,
                            "arg_names": arg_names,
                        }
        return procedures

    def _parse_sprite_to_actions(
        self, sprite_name, blocks, all_blocks, initial_variable_state, procedures
    ):
        start_block_id = self._find_start_block(blocks)
        if not start_block_id:
            return []
        self.has_any_valid_action = True
        pos_x, pos_y, pos_z = 0, 0, self.INITIAL_HOVER_HEIGHT_CM
        variable_state = initial_variable_state.copy()

        def _traverse_blocks(block_id, current_pos, current_vars, custom_block_args={}):
            px, py, pz = current_pos
            local_action_sequence = []
            current_block_id = block_id

            while current_block_id:
                block = all_blocks.get(current_block_id)
                if not block:
                    break
                opcode = block.get("opcode", "")
                inputs = block.get("inputs", {})
                canon_opcode = self._canonical_preview_opcode(opcode)

                if opcode in ("data_setvariableto", "data_changevariableby"):
                    var_name, var_id = block["fields"]["VARIABLE"]
                    value = self._get_input_value(
                        inputs.get("VALUE"), all_blocks, current_vars, custom_block_args
                    )
                    if opcode == "data_setvariableto":
                        current_vars[var_id] = value
                    else:
                        current_vars[var_id] = current_vars.get(var_id, 0.0) + value
                    current_block_id = block.get("next")
                    continue

                elif opcode == "procedures_call":
                    mutation = block.get("mutation", {})
                    proccode = mutation.get("proccode")
                    if proccode in procedures:
                        definition = procedures[proccode]
                        arg_ids_from_call = json.loads(
                            mutation.get("argumentids", "[]")
                        )

                        new_args = {}
                        for i, arg_id in enumerate(arg_ids_from_call):
                            input_val = self._get_input_value(
                                inputs.get(arg_id),
                                all_blocks,
                                current_vars,
                                custom_block_args,
                            )
                            if i < len(definition["arg_names"]):
                                arg_name = definition["arg_names"][i]
                                new_args[arg_name] = input_val

                        nested_actions, (px, py, pz), current_vars = _traverse_blocks(
                            definition["start_block_id"],
                            (px, py, pz),
                            current_vars,
                            custom_block_args=new_args,
                        )
                        local_action_sequence.extend(nested_actions)

                elif opcode in ("motion_turnright", "motion_turnleft"):
                    degrees = self._get_input_value(
                        inputs.get("DEGREES"),
                        all_blocks,
                        current_vars,
                        custom_block_args,
                    )
                    cmd_type = "cw" if opcode == "motion_turnright" else "ccw"
                    cmd = {
                        "target": sprite_name,
                        "command": f"{cmd_type} {int(degrees)}",
                    }
                    duration = 2.0 + (abs(degrees) / 90.0) * 1.5
                    local_action_sequence.append(
                        {
                            "duration": duration,
                            "commands": [cmd],
                            "is_wait": False,
                            "sprite_name": sprite_name,
                        }
                    )

                elif opcode == "event_broadcast":
                    message = self._get_broadcast_message(
                        inputs.get("BROADCAST_INPUT"), all_blocks
                    )
                    if message.lower().startswith("flip"):
                        parts = message.lower().split()
                        if len(parts) == 2 and parts[1] in ("l", "r", "f", "b"):
                            cmd = {"target": sprite_name, "command": f"flip {parts[1]}"}
                            local_action_sequence.append(
                                {
                                    "duration": 3.0,
                                    "commands": [cmd],
                                    "is_wait": False,
                                    "sprite_name": sprite_name,
                                }
                            )

                elif opcode in ("motion_gotoxy", "motion_movesteps"):
                    new_x, new_y = px, py
                    if opcode == "motion_gotoxy":
                        val_x = self._get_input_value(
                            inputs.get("X"), all_blocks, current_vars, custom_block_args
                        )
                        val_y = self._get_input_value(
                            inputs.get("Y"), all_blocks, current_vars, custom_block_args
                        )
                        new_x, new_y = val_x, val_y
                    else:
                        steps = self._get_input_value(
                            inputs.get("STEPS"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        new_y = py + steps
                    dx = int((new_x - px) * self.SCRATCH_TO_CM_RATE)
                    if abs(dx) >= self.MIN_TELLO_MOVE:
                        cmd, dur, _ = self._pos_to_command(sprite_name, dx, "h")
                        local_action_sequence.append(
                            {
                                "duration": dur,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                    dy = int((new_y - py) * self.SCRATCH_TO_CM_RATE)
                    if abs(dy) >= self.MIN_TELLO_MOVE:
                        cmd, dur, _ = self._pos_to_command(sprite_name, dy, "v")
                        local_action_sequence.append(
                            {
                                "duration": dur,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                    px, py = new_x, new_y
                elif opcode == "control_wait":
                    duration = self._get_input_value(
                        inputs.get("DURATION"),
                        all_blocks,
                        current_vars,
                        custom_block_args,
                    )
                    if duration > 0:
                        local_action_sequence.append(
                            {
                                "duration": duration,
                                "commands": [],
                                "is_wait": True,
                                "sprite_name": sprite_name,
                            }
                        )
                elif opcode in ("looks_setsizeto", "looks_changesizeby"):
                    new_z = None
                    if opcode == "looks_setsizeto":
                        new_z = self._get_input_value(
                            inputs.get("SIZE"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                    else:
                        change = self._get_input_value(
                            inputs.get("CHANGE"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        new_z = pz + change
                    dz = int(new_z - pz)
                    if abs(dz) >= self.MIN_TELLO_MOVE:
                        cmd, dur, _ = self._height_to_command(sprite_name, dz)
                        local_action_sequence.append(
                            {
                                "duration": dur,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                    pz = new_z
                elif opcode == "control_repeat":
                    times = round(
                        self._get_input_value(
                            inputs.get("TIMES"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                    )
                    substack_id = inputs.get("SUBSTACK", [None, None])[1]
                    if times > 0 and substack_id:
                        for _ in range(times):
                            nested_actions, (px, py, pz), current_vars = (
                                _traverse_blocks(
                                    substack_id,
                                    (px, py, pz),
                                    current_vars,
                                    custom_block_args,
                                )
                            )
                            local_action_sequence.extend(nested_actions)
                elif opcode == "control_forever":
                    substack_id = inputs.get("SUBSTACK", [None, None])[1]
                    if substack_id:
                        for _ in range(10):
                            nested_actions, (px, py, pz), current_vars = (
                                _traverse_blocks(
                                    substack_id,
                                    (px, py, pz),
                                    current_vars,
                                    custom_block_args,
                                )
                            )
                            local_action_sequence.extend(nested_actions)

                elif canon_opcode.startswith("preview_"):
                    self.log_parse(
                        f"Parsing preview block: original={opcode} canonical={canon_opcode}",
                        level="DEBUG",
                    )
                    if canon_opcode == "preview_setStageSize":
                        width = self._get_input_value(
                            inputs.get("WIDTH"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        height = self._get_input_value(
                            inputs.get("HEIGHT"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        cmd = {
                            "target": sprite_name,
                            "action": "set_stage_size",
                            "parameters": {"width": width, "height": height},
                        }
                        local_action_sequence.append(
                            {
                                "duration": 0.5,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                        self.log_parse(f"Added action: {cmd}", level="DEBUG")

                    elif canon_opcode == "preview_turnRight":
                        degrees = self._get_input_value(
                            inputs.get("DEGREES"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        cmd = {
                            "target": sprite_name,
                            "action": "turn_right",
                            "parameters": {"degrees": degrees},
                        }
                        local_action_sequence.append(
                            {
                                "duration": max(0.5, abs(degrees) / 90.0 * 0.8),
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                        self.log_parse(f"Added action: {cmd}", level="DEBUG")

                    elif canon_opcode == "preview_moveBy":
                        dx = self._get_input_value(
                            inputs.get("DX"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        dy = self._get_input_value(
                            inputs.get("DY"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        cmd = {
                            "target": sprite_name,
                            "action": "move_by",
                            "parameters": {"dx": dx, "dy": dy},
                        }
                        duration = max(0.5, (abs(dx) + abs(dy)) / 100.0)
                        local_action_sequence.append(
                            {
                                "duration": duration,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                        self.log_parse(f"Added action: {cmd}", level="DEBUG")

                    elif canon_opcode == "preview_moveXBy":
                        dx = self._get_input_value(
                            inputs.get("DX"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        cmd = {
                            "target": sprite_name,
                            "action": "move_by",
                            "parameters": {"dx": dx, "dy": 0},
                        }
                        duration = max(0.5, abs(dx) / 100.0)
                        local_action_sequence.append(
                            {
                                "duration": duration,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                        self.log_parse(f"Added action: {cmd}", level="DEBUG")

                    elif canon_opcode == "preview_moveYBy":
                        dy = self._get_input_value(
                            inputs.get("DY"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        cmd = {
                            "target": sprite_name,
                            "action": "move_by",
                            "parameters": {"dx": 0, "dy": dy},
                        }
                        duration = max(0.5, abs(dy) / 100.0)
                        local_action_sequence.append(
                            {
                                "duration": duration,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                        self.log_parse(f"Added action: {cmd}", level="DEBUG")

                    elif canon_opcode == "preview_moveToLocal":
                        lx = self._get_input_value(
                            inputs.get("LX"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        ly = self._get_input_value(
                            inputs.get("LY"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        cmd = {
                            "target": sprite_name,
                            "action": "move_to_local",
                            "parameters": {"lx": lx, "ly": ly},
                        }
                        duration = max(0.5, (abs(lx) + abs(ly)) / 100.0)
                        local_action_sequence.append(
                            {
                                "duration": duration,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                        self.log_parse(f"Added action: {cmd}", level="DEBUG")

                    elif canon_opcode == "preview_changeSizeBy":
                        change = self._get_input_value(
                            inputs.get("CHANGE") or inputs.get("DELTA"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        cmd = {
                            "target": sprite_name,
                            "action": "change_size_by",
                            "parameters": {"change": change},
                        }
                        duration = max(0.3, abs(change) / 50.0)
                        local_action_sequence.append(
                            {
                                "duration": duration,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                        self.log(f"Added action: {cmd}", level="DEBUG")

                    elif canon_opcode == "preview_setSizeTo":
                        size = self._get_input_value(
                            inputs.get("SIZE"),
                            all_blocks,
                            current_vars,
                            custom_block_args,
                        )
                        cmd = {
                            "target": sprite_name,
                            "action": "set_size_to",
                            "parameters": {"size": size},
                        }
                        local_action_sequence.append(
                            {
                                "duration": 0.3,
                                "commands": [cmd],
                                "is_wait": False,
                                "sprite_name": sprite_name,
                            }
                        )
                        self.log(f"Added action: {cmd}", level="DEBUG")

                    # Add more preview_* block handling as needed

                current_block_id = block.get("next")
            return local_action_sequence, (px, py, pz), current_vars

        return _traverse_blocks(start_block_id, (pos_x, pos_y, pos_z), variable_state)[
            0
        ]

    def parse_to_schedule(self):
        if not self.project_data:
            return [], 0.0
        final_event_list = [
            {
                "time": 0.0,
                "type": "TAKEOFF",
                "target": "システム",
                "text": f"離陸シーケンス ({self.TAKEOFF_DURATION:.1f}秒)",
            }
        ]
        master_time = self.TAKEOFF_DURATION
        all_actions, all_blocks = {}, {
            k: v
            for t in self.project_data.get("targets", [])
            for k, v in t.get("blocks", {}).items()
        }

        initial_variable_state = {}
        for target in self.project_data.get("targets", []):
            for var_id, var_data in target.get("variables", {}).items():
                try:
                    initial_value = float(var_data[1])
                except (ValueError, TypeError):
                    initial_value = 0.0
                initial_variable_state[var_id] = initial_value

        for target in self.project_data.get("targets", []):
            if target.get("isStage", False):
                continue
            sprite_name = target.get("name")
            blocks = target.get("blocks", {})
            procedures_for_this_sprite = self._find_procedure_definitions_for_target(
                blocks, all_blocks
            )

            actions = self._parse_sprite_to_actions(
                sprite_name,
                blocks,
                all_blocks,
                initial_variable_state,
                procedures_for_this_sprite,
            )
            if actions:
                all_actions[sprite_name] = actions

        # ★★★ 修正点: 着陸イベントで使うため、動作があるドローン名を控えておく ★★★
        drones_with_actions = list(all_actions.keys())

        while any(all_actions.values()):
            max_duration_this_step, actions_this_step = 0.0, []
            for sprite_name, action_list in all_actions.items():
                if action_list:
                    action = action_list.pop(0)
                    # サイズ変更系 (ステージ/スプライト) はタイムラインや飛行時間に含めない
                    cmds = action.get("commands", [])
                    size_actions = {"set_stage_size", "change_size_by", "set_size_to"}
                    if cmds and all(
                        isinstance(c, dict) and c.get("action") in size_actions
                        for c in cmds
                    ):
                        self.log_parse(
                            f"Ignored size-change action for timeline (target: {action.get('sprite_name')})",
                            level="DEBUG",
                        )
                        # スキップして次のスプライトへ（時間に影響させない）
                        continue

                    actions_this_step.append(action)
                    max_duration_this_step = max(
                        max_duration_this_step, action["duration"]
                    )
            for action in actions_this_step:
                if (
                    action.get("is_wait")
                    and action["duration"] < max_duration_this_step
                ):
                    msg = f"[{action['sprite_name']}] 待機時間がステップ最長動作より短いため延長されます。"
                    final_event_list.append(
                        {"time": master_time, "type": "WARNING", "text": msg}
                    )
                if action.get("is_wait"):
                    final_event_list.append(
                        {
                            "time": master_time,
                            "type": "WAIT",
                            "target": action["sprite_name"],
                            "text": f"{action['duration']:.2f}秒 待機",
                        }
                    )
                for cmd in action.get("commands", []):
                    # 出力用の説明を作成して解析ログに流す
                    desc = self._describe_command(cmd)
                    self.log_parse(
                        f"実行：{desc} (対象: {cmd.get('target')})", level="INFO"
                    )
                    # タイムライン表示用テキストを追加
                    cmd_text = desc
                    cmd.update(
                        {"time": master_time, "type": "COMMAND", "text": cmd_text}
                    )
                    final_event_list.append(cmd)
            master_time += max_duration_this_step

        # ★★★ 修正点: タイムラインの最後に着陸イベントを追加 ★★★
        if self.has_any_valid_action and drones_with_actions:
            land_time = master_time + 0.1  # 最後のイベントの直後に設定
            land_event = {
                "time": land_time,
                "type": "LAND",
                "target": "ALL",
                "text": f"着陸 (対象: {', '.join(drones_with_actions)})",
                "command": "land",
            }
            final_event_list.append(land_event)
            master_time = land_time  # 総時間も更新
        # ★★★ 修正ここまで ★★★

        final_event_list.sort(
            key=lambda x: (x["time"], 0 if x["type"] == "WARNING" else 1)
        )
        return final_event_list, master_time

    def _find_start_block(self, blocks):
        for block_id, block in blocks.items():
            # ★★★★★ こちらにも同様の安全チェックを追加 ★★★★★
            if (
                isinstance(block, dict)
                and block.get("opcode") == "event_whenflagclicked"
            ):
                return block.get("next")
        return None

    def _calculate_realistic_duration(self, distance, speed):
        if distance == 0:
            return 0.0
        calculated_time = (distance / speed) + self.MOVE_TIME_OVERHEAD
        return max(calculated_time, self.MINIMUM_MOVE_TIME)

    def _pos_to_command(self, name, distance, direction_type):
        if direction_type == "h":
            cmd = {
                "target": name,
                "command": f"{'right' if distance > 0 else 'left'} {abs(distance)}",
            }
            duration = self._calculate_realistic_duration(
                abs(distance), self.TELLO_HORIZONTAL_SPEED_CMS
            )
        else:
            cmd = {
                "target": name,
                "command": f"{'forward' if distance > 0 else 'back'} {abs(distance)}",
            }
            duration = self._calculate_realistic_duration(
                abs(distance), self.TELLO_HORIZONTAL_SPEED_CMS
            )
        return cmd, duration, []

    def _height_to_command(self, name, distance):
        direction = "up" if distance > 0 else "down"
        cmd = {"target": name, "command": f"{direction} {abs(distance)}"}
        duration = self._calculate_realistic_duration(
            abs(distance), self.TELLO_VERTICAL_SPEED_CMS
        )
        return cmd, duration, []
