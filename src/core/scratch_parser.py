import zipfile
import json
import math

class ScratchProjectParser:
    def __init__(self, sb3_path, log_queue):
        self.TAKEOFF_DURATION = 8.0
        self.MIN_TELLO_MOVE = 20; self.SCRATCH_TO_CM_RATE = 1; self.INITIAL_HOVER_HEIGHT_CM = 80
        self.TELLO_HORIZONTAL_SPEED_CMS = 50.0; self.TELLO_VERTICAL_SPEED_CMS = 40.0
        self.MOVE_TIME_OVERHEAD = 0.75; self.MINIMUM_MOVE_TIME = 1.5
        self.sb3_path = sb3_path; self.log_queue = log_queue
        self.project_data = self._load_project_data()
        self.has_any_valid_action = False
    
    def log(self, message, level="INFO"): self.log_queue.put({"level": level, "message": message})

    def _load_project_data(self):
        try:
            with zipfile.ZipFile(self.sb3_path, 'r') as z:
                with z.open('project.json') as f: return json.load(f)
        except Exception as e: self.log(f"エラー: {self.sb3_path} の読み込みまたは解析に失敗しました。 -> {e}", level="ERROR"); return None

    def _get_input_value(self, block_input, blocks, variable_state, custom_block_args):
        if not block_input: return 0.0
        input_type, input_value = block_input[0], block_input[1]

        if input_type in [1, 2]:
            if isinstance(input_value, list):
                try: return float(input_value[1])
                except (ValueError, TypeError): return 0.0
            if isinstance(input_value, str):
                ref_block = blocks.get(input_value)
                if not isinstance(ref_block, dict): return 0.0
                
                opcode = ref_block.get('opcode', '')
                if opcode == 'argument_reporter_string_number':
                    arg_name = ref_block['fields']['VALUE'][0]
                    return custom_block_args.get(arg_name, 0.0)
                
                if opcode == 'math_number':
                    try: return float(ref_block['fields']['NUM'][0])
                    except (ValueError, TypeError): return 0.0
        
        elif input_type == 3 and isinstance(input_value, list) and input_value[0] == 12:
            var_id = input_value[2]
            return variable_state.get(var_id, 0.0)
        
        return 0.0
    
    def _get_broadcast_message(self, block_input, blocks):
        if not block_input: return ""
        if block_input[0] == 1 and isinstance(block_input[1], str):
            ref_block = blocks.get(block_input[1])
            if isinstance(ref_block, dict) and ref_block.get('opcode') == 'event_broadcast_menu':
                return ref_block['fields']['BROADCAST_OPTION'][0]
        return ""

    def _find_procedure_definitions_for_target(self, target_blocks, all_blocks):
        procedures = {}
        for block_id, block in target_blocks.items():
            # ★★★★★ ここがエラーの原因でした！安全チェックを追加 ★★★★★
            # blockが辞書(ブロック情報)でない場合(リストなど)はスキップ
            if not isinstance(block, dict):
                continue

            if block.get('opcode') == 'procedures_definition':
                prototype_id = block.get('inputs', {}).get('custom_block', [None, None])[1]
                if prototype_id and prototype_id in all_blocks:
                    prototype_block = all_blocks[prototype_id]
                    mutation = prototype_block.get('mutation', {})
                    proccode = mutation.get('proccode')
                    if proccode:
                        arg_ids = json.loads(mutation.get('argumentids', '[]'))
                        arg_names = json.loads(mutation.get('argumentnames', '[]'))
                        
                        procedures[proccode] = {
                            'start_block_id': block.get('next'),
                            'arg_ids': arg_ids,
                            'arg_names': arg_names,
                        }
        return procedures

    def _parse_sprite_to_actions(self, sprite_name, blocks, all_blocks, initial_variable_state, procedures):
        start_block_id = self._find_start_block(blocks)
        if not start_block_id: return []
        self.has_any_valid_action = True
        pos_x, pos_y, pos_z = 0, 0, self.INITIAL_HOVER_HEIGHT_CM
        variable_state = initial_variable_state.copy()

        def _traverse_blocks(block_id, current_pos, current_vars, custom_block_args={}):
            px, py, pz = current_pos; local_action_sequence = []; current_block_id = block_id
            
            while current_block_id:
                block = all_blocks.get(current_block_id)
                if not block: break
                opcode = block.get('opcode', ''); inputs = block.get('inputs', {})

                if opcode in ('data_setvariableto', 'data_changevariableby'):
                    var_name, var_id = block['fields']['VARIABLE']
                    value = self._get_input_value(inputs.get('VALUE'), all_blocks, current_vars, custom_block_args)
                    if opcode == 'data_setvariableto': current_vars[var_id] = value
                    else: current_vars[var_id] = current_vars.get(var_id, 0.0) + value
                    current_block_id = block.get('next'); continue

                elif opcode == 'procedures_call':
                    mutation = block.get('mutation', {})
                    proccode = mutation.get('proccode')
                    if proccode in procedures:
                        definition = procedures[proccode]
                        arg_ids_from_call = json.loads(mutation.get('argumentids', '[]'))
                        
                        new_args = {}
                        for i, arg_id in enumerate(arg_ids_from_call):
                            input_val = self._get_input_value(inputs.get(arg_id), all_blocks, current_vars, custom_block_args)
                            if i < len(definition['arg_names']):
                                arg_name = definition['arg_names'][i]
                                new_args[arg_name] = input_val
                        
                        nested_actions, (px, py, pz), current_vars = _traverse_blocks(definition['start_block_id'], (px, py, pz), current_vars, custom_block_args=new_args)
                        local_action_sequence.extend(nested_actions)

                elif opcode in ('motion_turnright', 'motion_turnleft'):
                    degrees = self._get_input_value(inputs.get('DEGREES'), all_blocks, current_vars, custom_block_args)
                    cmd_type = 'cw' if opcode == 'motion_turnright' else 'ccw'
                    cmd = {'target': sprite_name, 'command': f"{cmd_type} {int(degrees)}"}
                    duration = 2.0 + (abs(degrees) / 90.0) * 1.5
                    local_action_sequence.append({'duration': duration, 'commands': [cmd], 'is_wait': False, 'sprite_name': sprite_name})
                
                elif opcode == 'event_broadcast':
                    message = self._get_broadcast_message(inputs.get('BROADCAST_INPUT'), all_blocks)
                    if message.lower().startswith("flip"):
                        parts = message.lower().split()
                        if len(parts) == 2 and parts[1] in ('l', 'r', 'f', 'b'):
                            cmd = {'target': sprite_name, 'command': f"flip {parts[1]}"}
                            local_action_sequence.append({'duration': 3.0, 'commands': [cmd], 'is_wait': False, 'sprite_name': sprite_name})

                elif opcode in ('motion_gotoxy', 'motion_movesteps'):
                    new_x, new_y = px, py
                    if opcode == 'motion_gotoxy':
                        val_x = self._get_input_value(inputs.get('X'), all_blocks, current_vars, custom_block_args)
                        val_y = self._get_input_value(inputs.get('Y'), all_blocks, current_vars, custom_block_args)
                        new_x, new_y = val_x, val_y
                    else: 
                        steps = self._get_input_value(inputs.get('STEPS'), all_blocks, current_vars, custom_block_args)
                        new_y = py + steps
                    dx = int((new_x - px) * self.SCRATCH_TO_CM_RATE)
                    if abs(dx) >= self.MIN_TELLO_MOVE: cmd, dur, _ = self._pos_to_command(sprite_name, dx, 'h'); local_action_sequence.append({'duration': dur, 'commands': [cmd], 'is_wait': False, 'sprite_name': sprite_name})
                    dy = int((new_y - py) * self.SCRATCH_TO_CM_RATE)
                    if abs(dy) >= self.MIN_TELLO_MOVE: cmd, dur, _ = self._pos_to_command(sprite_name, dy, 'v'); local_action_sequence.append({'duration': dur, 'commands': [cmd], 'is_wait': False, 'sprite_name': sprite_name})
                    px, py = new_x, new_y
                elif opcode == 'control_wait':
                    duration = self._get_input_value(inputs.get('DURATION'), all_blocks, current_vars, custom_block_args)
                    if duration > 0: local_action_sequence.append({'duration': duration, 'commands': [], 'is_wait': True, 'sprite_name': sprite_name})
                elif opcode in ('looks_setsizeto', 'looks_changesizeby'):
                    new_z = None
                    if opcode == 'looks_setsizeto': new_z = self._get_input_value(inputs.get('SIZE'), all_blocks, current_vars, custom_block_args)
                    else: 
                        change = self._get_input_value(inputs.get('CHANGE'), all_blocks, current_vars, custom_block_args)
                        new_z = pz + change
                    dz = int(new_z - pz)
                    if abs(dz) >= self.MIN_TELLO_MOVE: cmd, dur, _ = self._height_to_command(sprite_name, dz); local_action_sequence.append({'duration': dur, 'commands': [cmd], 'is_wait': False, 'sprite_name': sprite_name})
                    pz = new_z
                elif opcode == 'control_repeat':
                    times = round(self._get_input_value(inputs.get('TIMES'), all_blocks, current_vars, custom_block_args))
                    substack_id = inputs.get('SUBSTACK', [None, None])[1]
                    if times > 0 and substack_id:
                        for _ in range(times): 
                            nested_actions, (px, py, pz), current_vars = _traverse_blocks(substack_id, (px, py, pz), current_vars, custom_block_args)
                            local_action_sequence.extend(nested_actions)
                elif opcode == 'control_forever':
                    substack_id = inputs.get('SUBSTACK', [None, None])[1]
                    if substack_id:
                        for _ in range(10): 
                            nested_actions, (px, py, pz), current_vars = _traverse_blocks(substack_id, (px, py, pz), current_vars, custom_block_args)
                            local_action_sequence.extend(nested_actions)
                
                current_block_id = block.get('next')
            return local_action_sequence, (px, py, pz), current_vars

        return _traverse_blocks(start_block_id, (pos_x, pos_y, pos_z), variable_state)[0]

    def parse_to_schedule(self):
        if not self.project_data: return [], 0.0
        final_event_list = [{'time': 0.0, 'type': 'TAKEOFF', 'target': 'システム', 'text': f'離陸シーケンス ({self.TAKEOFF_DURATION:.1f}秒)'}]
        master_time = self.TAKEOFF_DURATION
        all_actions, all_blocks = {}, {k: v for t in self.project_data.get('targets', []) for k, v in t.get('blocks', {}).items()}
        
        initial_variable_state = {}
        for target in self.project_data.get('targets', []):
            for var_id, var_data in target.get('variables', {}).items():
                try: initial_value = float(var_data[1])
                except (ValueError, TypeError): initial_value = 0.0
                initial_variable_state[var_id] = initial_value

        for target in self.project_data.get('targets', []):
            if target.get('isStage', False): continue
            sprite_name = target.get('name')
            blocks = target.get('blocks', {})
            procedures_for_this_sprite = self._find_procedure_definitions_for_target(blocks, all_blocks)
            
            actions = self._parse_sprite_to_actions(sprite_name, blocks, all_blocks, initial_variable_state, procedures_for_this_sprite)
            if actions:
                all_actions[sprite_name] = actions
        
        # ★★★ 修正点: 着陸イベントで使うため、動作があるドローン名を控えておく ★★★
        drones_with_actions = list(all_actions.keys())

        while any(all_actions.values()):
            max_duration_this_step, actions_this_step = 0.0, []
            for sprite_name, action_list in all_actions.items():
                if action_list: action = action_list.pop(0); actions_this_step.append(action); max_duration_this_step = max(max_duration_this_step, action['duration'])
            for action in actions_this_step:
                if action.get('is_wait') and action['duration'] < max_duration_this_step:
                    msg = (f"[{action['sprite_name']}] 待機時間がステップ最長動作より短いため延長されます。")
                    final_event_list.append({'time': master_time, 'type': 'WARNING', 'text': msg})
                if action.get('is_wait'): final_event_list.append({'time': master_time, 'type': 'WAIT', 'target': action['sprite_name'], 'text': f"{action['duration']:.2f}秒 待機"})
                for cmd in action.get('commands', []): cmd.update({'time': master_time, 'type': 'COMMAND'}); final_event_list.append(cmd)
            master_time += max_duration_this_step
        
        # ★★★ 修正点: タイムラインの最後に着陸イベントを追加 ★★★
        if self.has_any_valid_action and drones_with_actions:
            land_time = master_time + 0.1  # 最後のイベントの直後に設定
            land_event = {
                'time': land_time,
                'type': 'LAND',
                'target': 'ALL',
                'text': f"着陸 (対象: {', '.join(drones_with_actions)})",
                'command': 'land'
            }
            final_event_list.append(land_event)
            master_time = land_time  # 総時間も更新
        # ★★★ 修正ここまで ★★★

        final_event_list.sort(key=lambda x: (x['time'], 0 if x['type'] == 'WARNING' else 1))
        return final_event_list, master_time

    def _find_start_block(self, blocks):
        for block_id, block in blocks.items():
            # ★★★★★ こちらにも同様の安全チェックを追加 ★★★★★
            if isinstance(block, dict) and block.get('opcode') == 'event_whenflagclicked':
                return block.get('next')
        return None

    def _calculate_realistic_duration(self, distance, speed):
        if distance == 0: return 0.0
        calculated_time = (distance / speed) + self.MOVE_TIME_OVERHEAD
        return max(calculated_time, self.MINIMUM_MOVE_TIME)

    def _pos_to_command(self, name, distance, direction_type):
        if direction_type == 'h': cmd = {'target': name, 'command': f"{'right' if distance > 0 else 'left'} {abs(distance)}"}; duration = self._calculate_realistic_duration(abs(distance), self.TELLO_HORIZONTAL_SPEED_CMS)
        else: cmd = {'target': name, 'command': f"{'forward' if distance > 0 else 'back'} {abs(distance)}"}; duration = self._calculate_realistic_duration(abs(distance), self.TELLO_HORIZONTAL_SPEED_CMS)
        return cmd, duration, []

    def _height_to_command(self, name, distance):
        direction = 'up' if distance > 0 else 'down'; cmd = {'target': name, 'command': f"{direction} {abs(distance)}"}; duration = self._calculate_realistic_duration(abs(distance), self.TELLO_VERTICAL_SPEED_CMS)
        return cmd, duration, []