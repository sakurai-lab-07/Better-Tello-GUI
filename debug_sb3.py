import zipfile
import json
import sys

sb3_path = sys.argv[1] if len(sys.argv) > 1 else "test_project/1_Tello.sb3"

try:
    with zipfile.ZipFile(sb3_path, "r") as z:
        data = json.load(z.open("project.json"))

    targets = data.get("targets", [])

    print("=== Block Chain Analysis ===\n")

    for target in targets:
        if target.get("isStage"):
            continue

        sprite_name = target.get("name")
        blocks = target.get("blocks", {})

        print(f"Sprite: {sprite_name}")
        print(f"Total blocks: {len(blocks)}\n")

        # Print all blocks with their structure
        print("Block details:")
        for block_id, block in sorted(blocks.items()):
            if isinstance(block, dict):
                opcode = block.get("opcode", "")
                next_id = block.get("next")
                inputs = block.get("inputs", {})
                print(f"  ID: {block_id}")
                print(f"    Opcode: {opcode}")
                print(f"    Next: {next_id}")
                if inputs:
                    print(f"    Inputs: {list(inputs.keys())}")
                print()

        # Find the event_whenflagclicked block
        print("\n=== Execution Chain ===")
        for block_id, block in blocks.items():
            if (
                isinstance(block, dict)
                and block.get("opcode") == "event_whenflagclicked"
            ):
                print(f"Start block (flag clicked): {block_id}")
                next_id = block.get("next")

                if next_id:
                    print(f"  → Next: {next_id}")
                    current = next_id
                    count = 0
                    while current and count < 20:
                        if current in blocks:
                            curr_block = blocks[current]
                            if isinstance(curr_block, dict):
                                curr_opcode = curr_block.get("opcode")
                                curr_next = curr_block.get("next")
                                print(f"  [{count}] {current}: {curr_opcode}")
                                print(f"       → Next: {curr_next}")
                                current = curr_next
                                count += 1
                            else:
                                print(f"  [{count}] {current}: NOT A DICT")
                                break
                        else:
                            print(f"  [{count}] {current}: BLOCK NOT FOUND")
                            break
                else:
                    print("  No next block!")
                break

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
