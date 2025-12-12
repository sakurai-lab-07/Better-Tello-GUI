#!/usr/bin/env python
"""パーサーのテスト"""
import sys
import queue
from src.scratch_parser import ScratchProjectParser

log_queue = queue.Queue()

# パーサー作成
parser = ScratchProjectParser("test_project/1_Tello.sb3", log_queue)

# タイムラインを解析
print("=== Parse to Schedule ===")
events, total_time = parser.parse_to_schedule()

# ログを表示する（解析後）
print("\n=== Parsing Logs ===")
while not log_queue.empty():
    msg = log_queue.get()
    print(f"[{msg.get('level', 'INFO')}] {msg.get('message', '')}")

print(f"\nTotal events: {len(events)}")
print(f"Total time: {total_time}s\n")

for event in events:
    event_type = event.get("type")
    time = event.get("time", 0)
    if event_type in ["COMMAND", "WAIT", "LAND"]:
        target = event.get("target", "?")
        text = event.get("text", event.get("command", ""))
        print(f"[{time:6.2f}s] {event_type:10} {target:10} {text}")
    elif event_type == "INFO":
        target = event.get("target", "?")
        text = event.get("text", "")
        print(f"[{time:6.2f}s] {event_type:10} {target:10} {text}")
    else:
        print(f"[{time:6.2f}s] {event_type:10} {event.get('text', '')}")
