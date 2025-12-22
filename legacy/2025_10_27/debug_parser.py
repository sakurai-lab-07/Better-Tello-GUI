# debug_parser.py
import sys
from queue import Queue
import pprint
from scratch_parser import ScratchProjectParser

# ダミーのログキュー
dummy_queue = Queue()

def main():
    if len(sys.argv) < 2:
        print("エラー: Scratchの.sb3ファイルのパスを指定してください。")
        print(r'使い方: python debug_parser.py "C:\path\to\your\file.sb3"')
        return

    sb3_path = sys.argv[1]
    print(f"--- 解析を開始します: {sb3_path} ---\n")

    # パーサーを単体で実行
    parser = ScratchProjectParser(sb3_path, dummy_queue)
    schedule, total_time = parser.parse_to_schedule()

    print("--- 解析結果 ---")
    pprint.pprint(schedule)
    print(f"\n--- 予想総時間 ---")
    print(f"{total_time:.2f}秒")

if __name__ == '__main__':
    main()