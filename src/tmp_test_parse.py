import sys
from queue import Queue

sys.path.insert(0, "src")
from core.scratch_parser import ScratchProjectParser

q = Queue()
# 引数で .sb3 パスを受け取る。指定がなければ test-case/1_Tello.sb3 を使う
sb3_path = sys.argv[1] if len(sys.argv) > 1 else "test-case/1_Tello.sb3"
parser = ScratchProjectParser(sb3_path, q)
events, total = parser.parse_to_schedule()
print("events=", len(events), "total_time=", total)
for e in events:
    print(
        f"{e.get('time'):.2f}s | {e.get('type'):7} | {e.get('target',''):8} | {e.get('text', e.get('command', ''))}"
    )
print("\n--- log queue ---")
while not q.empty():
    print(q.get())
