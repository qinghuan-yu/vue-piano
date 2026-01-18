"""
修复切片Token合并MIDI的脚本

问题：
1. training_sequence包含[BOS] Source [SEP] Target [EOS]，直接转换会生成双倍时长
2. 切片没有加绝对时间偏移，导致所有切片堆叠在开头

解决方案：
1. 只提取SEP之后的Target部分
2. 为每个切片的音符添加start_time偏移
"""

import json
import sys
import pretty_midi

# 导入主程序的tokens_to_notes函数
sys.path.append('.')
from main import tokens_to_notes


def reconstruct_midi_from_slices(json_file='tokens_sliced.json', output_file='merged_fixed.mid'):
    """
    从切片Token JSON文件重建完整MIDI
    
    Args:
        json_file: 输入的切片Token JSON文件路径
        output_file: 输出的MIDI文件路径
    """
    print("=" * 70)
    print("Reconstructing MIDI from Token Slices")
    print("=" * 70)
    
    # 1. 加载切片数据
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: File {json_file} not found!")
        return
    
    samples = data.get('samples', [])
    time_quantization = data.get('time_quantization_ms', 10)
    
    print(f"\nLoaded {len(samples)} slices")
    print(f"Time quantization: {time_quantization}ms")
    print(f"Total duration: {data.get('total_duration', 0):.2f}s")
    
    # 2. 准备MIDI对象
    pm = pretty_midi.PrettyMIDI()
    piano = pretty_midi.Instrument(program=0, name="Animenz Piano")
    
    total_notes = 0
    
    # 3. 逐个处理切片
    for idx, sample in enumerate(samples):
        slice_id = sample['slice_id']
        start_time = sample['start_time']
        end_time = sample['end_time']
        
        print(f"\nProcessing slice {slice_id}: {start_time:.1f}s - {end_time:.1f}s")
        
        # --- 关键步骤A: 只提取Target部分 ---
        seq = sample['training_sequence']
        
        try:
            # 找到分隔符<SEP> (Token ID=2)的位置
            sep_index = seq.index(2)
            
            # 只取SEP之后的内容（这是完整编曲的Target部分）
            target_tokens = seq[sep_index + 1:]
            
            # 去掉末尾的<EOS> (Token ID=3)
            if target_tokens and target_tokens[-1] == 3:
                target_tokens = target_tokens[:-1]
            
            print(f"  Extracted {len(target_tokens)} target tokens (after SEP)")
            
        except ValueError:
            print(f"  WARNING: Slice {slice_id} has no SEP token, skipping!")
            continue
        
        # --- 转换Token -> Notes ---
        notes_list = tokens_to_notes(target_tokens, time_quantization=time_quantization)
        
        if not notes_list:
            print(f"  WARNING: No notes generated from tokens")
            continue
        
        print(f"  Generated {len(notes_list)} notes")
        
        # --- 关键步骤B: 加上绝对时间偏移 ---
        offset = start_time
        
        for n in notes_list:
            # 创建pretty_midi音符对象，加上切片的起始时间偏移
            note = pretty_midi.Note(
                velocity=n['velocity'],
                pitch=n['pitch'],
                start=n['start'] + offset,  # 加上切片开始时间
                end=n['end'] + offset       # 加上切片开始时间
            )
            piano.notes.append(note)
            total_notes += 1
        
        # 显示时间范围验证
        if notes_list:
            first_note = notes_list[0]['start'] + offset
            last_note = max(n['end'] for n in notes_list) + offset
            print(f"  Time range: {first_note:.2f}s - {last_note:.2f}s")
    
    # 4. 添加乐器到MIDI
    pm.instruments.append(piano)
    
    # 5. 保存文件
    pm.write(output_file)
    
    print("\n" + "=" * 70)
    print(f"SUCCESS: Saved {total_notes} notes to {output_file}")
    print(f"Total MIDI duration: {pm.get_end_time():.2f}s")
    print("=" * 70)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Reconstruct MIDI from sliced tokens')
    parser.add_argument('-i', '--input', default='tokens_sliced.json',
                        help='Input JSON file (default: tokens_sliced.json)')
    parser.add_argument('-o', '--output', default='merged_fixed.mid',
                        help='Output MIDI file (default: merged_fixed.mid)')
    
    args = parser.parse_args()
    
    reconstruct_midi_from_slices(args.input, args.output)


if __name__ == "__main__":
    main()
