"""
测试Token转MIDI的功能
"""
import json
import sys
sys.path.append('backend')

from main import tokens_to_midi

# 测试简单的token序列
test_tokens = [
    1,  # BOS
    10, 60,  # NOTE_ON melody C4
    0, 4,    # TIME 400ms
    11, 60,  # NOTE_OFF melody C4
    10, 64,  # NOTE_ON melody E4
    0, 4,    # TIME 400ms
    11, 64,  # NOTE_OFF melody E4
    2,  # SEP
    10, 60,  # NOTE_ON melody C4
    0, 4,    # TIME 400ms
    11, 60,  # NOTE_OFF melody C4
    20, 48,  # NOTE_ON accomp C3
    10, 64,  # NOTE_ON melody E4
    0, 4,    # TIME 400ms
    11, 64,  # NOTE_OFF melody E4
    21, 48,  # NOTE_OFF accomp C3
    3   # EOS
]

print("测试Token转MIDI功能...")
notes = tokens_to_midi(test_tokens, time_quantization=100)

print(f"\n✅ 成功解析出 {len(notes)} 个音符：")
for i, note in enumerate(notes):
    note_type = "旋律" if note['is_melody'] else "伴奏"
    print(f"  {i+1}. [{note_type}] Pitch={note['pitch']}, Start={note['start']:.2f}s, End={note['end']:.2f}s")

print("\n测试通过！")
