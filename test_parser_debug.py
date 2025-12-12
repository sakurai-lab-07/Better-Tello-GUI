#!/usr/bin/env python
"""プロジェクトデータのテスト"""
import sys
import queue
from src.scratch_parser import ScratchProjectParser

log_queue = queue.Queue()

# パーサー作成
parser = ScratchProjectParser("test_project/1_Tello.sb3", log_queue)

# プロジェクトデータを確認
if parser.project_data:
    print("✓ Project data loaded")
    targets = parser.project_data.get("targets", [])
    print(f"  Targets: {len(targets)}")
    for target in targets:
        print(f"    - {target.get('name')} (isStage: {target.get('isStage')})")
else:
    print("✗ Project data failed to load")

# ログを確認
print("\nLogs from initialization:")
while not log_queue.empty():
    msg = log_queue.get()
    print(f"[{msg.get('level', 'INFO')}] {msg.get('message', '')}")
