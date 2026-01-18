"""
Melody-Annotator Backend
使用 FastAPI + pretty_midi 实现 MIDI 旋律分离
"""
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List, Dict
import pretty_midi
import numpy as np
import tempfile
import os
import io
import zipfile
from pydantic import BaseModel

app = FastAPI(title="Melody Annotator API")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Note(BaseModel):
    """音符数据模型"""
    id: int
    start: float
    end: float
    pitch: int
    velocity: int
    is_melody: bool


class MIDIData(BaseModel):
    """MIDI 数据模型"""
    duration: float
    notes: List[Note]


class ExportRequest(BaseModel):
    """导出请求模型"""
    notes: List[Note]
    duration: float


class TokenizeRequest(BaseModel):
    """Token化请求模型"""
    notes: List[Note]
    duration: float
    time_quantization: int = 10  # 时间量化单位（毫秒）- 提高精度以保留快速音符细节


class JsonToMidiRequest(BaseModel):
    """JSON转MIDI请求模型"""
    notes: List[Note]
    filename: str = "output.mid"


class TokensToMidiRequest(BaseModel):
    """Token序列转MIDI请求模型"""
    training_sequence: List[int]
    time_quantization: int = 10
    filename: str = "output.mid"


class TokenizeSlicedRequest(BaseModel):
    """切片Token化请求模型"""
    notes: List[Note]
    duration: float
    time_quantization: int = 10  # 时间量化单位（毫秒）- 10ms精度保留快速音符
    slice_duration: float = 8.0  # 每个切片的时长（秒）
    overlap: float = 0.0  # 切片之间的重叠时间（秒）


def slice_notes_by_time(notes: List[Dict], start_time: float, end_time: float) -> List[Dict]:
    """
    根据时间范围切片音符
    
    Args:
        notes: 音符列表
        start_time: 切片开始时间
        end_time: 切片结束时间
    
    Returns:
        在时间范围内的音符列表（时间已调整为相对于start_time）
    """
    sliced_notes = []
    
    for note in notes:
        # 检查音符是否在时间范围内
        if note['start'] < end_time and note['end'] > start_time:
            # 调整音符时间为相对于切片开始时间
            adjusted_note = note.copy()
            adjusted_note['start'] = max(0, note['start'] - start_time)
            adjusted_note['end'] = min(end_time - start_time, note['end'] - start_time)
            sliced_notes.append(adjusted_note)
    
    return sliced_notes


def extract_target_tokens(training_sequence: List[int]) -> List[int]:
    """
    从training_sequence中只提取Target部分
    
    training_sequence格式: [1] + Source + [2] + Target + [3]
    返回: Target部分 (不包含SEP和EOS)
    
    Args:
        training_sequence: 完整的训练序列
    
    Returns:
        只包含Target的token序列
    """
    try:
        # 找到SEP (Token ID=2)的位置
        sep_index = training_sequence.index(2)
        
        # 提取SEP之后的部分
        target_tokens = training_sequence[sep_index + 1:]
        
        # 去掉末尾的EOS (Token ID=3)
        if target_tokens and target_tokens[-1] == 3:
            target_tokens = target_tokens[:-1]
        
        return target_tokens
    except ValueError:
        # 如果没有SEP，返回整个序列（去掉BOS和EOS）
        result = training_sequence[:]
        if result and result[0] == 1:  # 去掉BOS
            result = result[1:]
        if result and result[-1] == 3:  # 去掉EOS
            result = result[:-1]
        return result


def tokens_to_notes(tokens: List[int], time_quantization: int = 10) -> List[Dict]:
    """
    将Token序列逆转换为MIDI音符列表（修复版）
    
    修复内容：
    1. 同音覆盖保护：同一音高连续NOTE_ON时，自动关闭上一个音符
    2. 零时长保护：强制最小持续时间，防止duration=0的音符
    3. 残余音符清理：序列结束时关闭所有未关闭的音符
    4. TIME token鲁棒性：处理异常的时间参数
    
    Token编码：
    - 1: <BOS>
    - 2: <SEP>
    - 3: <EOS>
    - 0, time_delta: TIME事件
    - 10, pitch: NOTE_ON (旋律)
    - 11, pitch: NOTE_OFF (旋律)
    - 20, pitch: NOTE_ON (伴奏)
    - 21, pitch: NOTE_OFF (伴奏)
    
    Args:
        tokens: Token序列
        time_quantization: 时间量化单位（毫秒），默认10ms以保留快速音符细节
    
    Returns:
        音符列表
    """
    notes = []
    active_notes = {}  # {pitch: {'start': time, 'is_melody': bool}}
    current_time = 0.0
    note_id = 0
    
    # 定义最小持续时间（秒），防止生成时长为0的音符
    MIN_DURATION = time_quantization / 1000.0 * 0.5
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        # 跳过特殊标记
        if token in [1, 2, 3]:  # <BOS>, <SEP>, <EOS>
            i += 1
            continue
        
        # -------------------------------------------------------
        # 1. TIME事件
        # -------------------------------------------------------
        if token == 0:
            if i + 1 < len(tokens):
                val = tokens[i + 1]
                # 【鲁棒性保护】如果后面跟的不是时间数值，而是其他命令
                # 假设event ID都在10以上，时间偏移通常较小
                if val in [10, 11, 20, 21]:
                    time_delta = 0
                    i += 1
                else:
                    time_delta = val
                    current_time += (time_delta * time_quantization) / 1000.0
                    i += 2
            else:
                i += 1
        
        # -------------------------------------------------------
        # 2. NOTE_ON (旋律=10, 伴奏=20)
        # -------------------------------------------------------
        elif token in [10, 20]:
            is_melody = (token == 10)
            if i + 1 < len(tokens):
                pitch = tokens[i + 1]
                
                # 【修复1：同音覆盖保护】
                # 如果这个音高已经在active_notes里了，说明上一个音没关掉
                # 强制把它关掉，作为上一个音的结束，再开始新音
                if pitch in active_notes:
                    prev_note = active_notes.pop(pitch)
                    start_t = prev_note['start']
                    end_t = current_time
                    # 只有当时长 > 0 时才保存，避免完全重叠的脏数据
                    if end_t > start_t:
                        notes.append({
                            'id': note_id,
                            'start': start_t,
                            'end': end_t,
                            'pitch': pitch,
                            'velocity': 80,
                            'is_melody': prev_note['is_melody']
                        })
                        note_id += 1
                
                # 记录新音符开始
                active_notes[pitch] = {
                    'start': current_time,
                    'is_melody': is_melody
                }
                i += 2
            else:
                i += 1
        
        # -------------------------------------------------------
        # 3. NOTE_OFF (旋律=11, 伴奏=21)
        # -------------------------------------------------------
        elif token in [11, 21]:
            # 不区分Melody Off还是Accomp Off，只要pitch对上了就关
            if i + 1 < len(tokens):
                pitch = tokens[i + 1]
                if pitch in active_notes:
                    note_info = active_notes.pop(pitch)
                    start_t = note_info['start']
                    end_t = current_time
                    
                    # 【修复2：最小时长保护】
                    # 如果start == end，强制给它加一点点长度
                    if end_t <= start_t:
                        end_t = start_t + MIN_DURATION
                    
                    notes.append({
                        'id': note_id,
                        'start': start_t,
                        'end': end_t,
                        'pitch': pitch,
                        'velocity': 80,
                        'is_melody': note_info['is_melody']
                    })
                    note_id += 1
                i += 2
            else:
                i += 1
        
        else:
            # 未知token，跳过
            i += 1
    
    # 【修复3：清理残余音符】
    # 如果序列结束了，active_notes里还有没关掉的音符
    # 强制在current_time关闭
    for pitch, info in active_notes.items():
        start_t = info['start']
        end_t = current_time
        if end_t <= start_t:
            end_t = start_t + MIN_DURATION
        
        notes.append({
            'id': note_id,
            'start': start_t,
            'end': end_t,
            'pitch': pitch,
            'velocity': 80,
            'is_melody': info['is_melody']
        })
        note_id += 1
    
    # 最后按开始时间排序
    notes.sort(key=lambda x: x['start'])
    return notes


def midi_to_tokens(notes: List[Dict], duration: float, time_quantization: int = 10, 
                   start_time: float = 0.0, end_time: float = None) -> Dict[str, List[int]]:
    """
    将 MIDI 音符转换为训练用的 Token 序列（纯数字格式）
    
    生成格式：[1] + Source + [2] + Target + [3]
    - Source: 只包含旋律音符的token
    - Target: 包含所有音符的token
    
    Token编码：
    - 1: <BOS>
    - 2: <SEP>
    - 3: <EOS>
    - 0, time_delta: TIME事件
    - 10, pitch: NOTE_ON (旋律)
    - 11, pitch: NOTE_OFF (旋律)
    - 20, pitch: NOTE_ON (伴奏)
    - 21, pitch: NOTE_OFF (伴奏)
    
    Args:
        notes: 音符列表
        duration: MIDI 总时长
        time_quantization: 时间量化单位（毫秒），默认10ms提供更高精度
        start_time: 切片开始时间（用于切片）
        end_time: 切片结束时间（用于切片）
    
    Returns:
        包含 source、target、training_sequence 的字典
    """
    # 如果指定了切片时间，则进行切片
    if end_time is not None:
        notes = slice_notes_by_time(notes, start_time, end_time)
    # 创建事件列表
    all_events = []
    melody_events = []
    
    for note in notes:
        # NOTE_ON 事件
        event_on = {
            'time': note['start'],
            'type': 'note_on',
            'pitch': note['pitch'],
            'velocity': note['velocity'],
            'is_melody': note['is_melody']
        }
        # NOTE_OFF 事件
        event_off = {
            'time': note['end'],
            'type': 'note_off',
            'pitch': note['pitch'],
            'velocity': 0,
            'is_melody': note['is_melody']
        }
        
        all_events.append(event_on)
        all_events.append(event_off)
        
        # 只添加旋律到melody_events
        if note['is_melody']:
            melody_events.append(event_on)
            melody_events.append(event_off)
    
    # 按时间排序
    all_events.sort(key=lambda x: (x['time'], x['type'] == 'note_off'))
    melody_events.sort(key=lambda x: (x['time'], x['type'] == 'note_off'))
    
    # 生成 Source tokens (仅旋律) - 纯数字格式
    source_tokens = []
    current_time = 0
    for event in melody_events:
        time_delta = int((event['time'] - current_time) * 1000 / time_quantization)
        if time_delta > 0:
            source_tokens.extend([0, time_delta])  # TIME事件
            current_time = event['time']
        
        if event['type'] == 'note_on':
            source_tokens.extend([10, event['pitch']])  # NOTE_ON (旋律)
        else:
            source_tokens.extend([11, event['pitch']])  # NOTE_OFF (旋律)
    
    # 生成 Target tokens (所有音符) - 纯数字格式
    target_tokens = []
    current_time = 0
    for event in all_events:
        time_delta = int((event['time'] - current_time) * 1000 / time_quantization)
        if time_delta > 0:
            target_tokens.extend([0, time_delta])  # TIME事件
            current_time = event['time']
        
        if event['is_melody']:
            if event['type'] == 'note_on':
                target_tokens.extend([10, event['pitch']])  # NOTE_ON (旋律)
            else:
                target_tokens.extend([11, event['pitch']])  # NOTE_OFF (旋律)
        else:
            if event['type'] == 'note_on':
                target_tokens.extend([20, event['pitch']])  # NOTE_ON (伴奏)
            else:
                target_tokens.extend([21, event['pitch']])  # NOTE_OFF (伴奏)
    
    # 拼接训练序列: [1] + Source + [2] + Target + [3]
    training_sequence = [1] + source_tokens + [2] + target_tokens + [3]
    
    return {
        "source": source_tokens,
        "target": target_tokens,
        "training_sequence": training_sequence
    }


def skyline_algorithm(notes: List[Dict], time_window: float = 0.05) -> List[Dict]:
    """
    Skyline 算法：在每个时间窗口内，标记音高最高的音符为主旋律
    
    Args:
        notes: 音符列表
        time_window: 时间窗口大小（秒）
    
    Returns:
        标注后的音符列表
    """
    if not notes:
        return notes
    
    # 获取最大结束时间
    max_time = max(note['end'] for note in notes)
    
    # 遍历每个时间窗口
    current_time = 0
    while current_time < max_time:
        window_end = current_time + time_window
        
        # 找到当前窗口内的所有音符
        notes_in_window = [
            note for note in notes
            if note['start'] < window_end and note['end'] > current_time
        ]
        
        if notes_in_window:
            # 找到最高音
            max_pitch = max(note['pitch'] for note in notes_in_window)
            
            # 标记最高音为旋律
            for note in notes_in_window:
                if note['pitch'] == max_pitch:
                    note['is_melody'] = True
        
        current_time += time_window
    
    return notes


@app.get("/")
async def root():
    """健康检查"""
    return {"message": "Melody Annotator API is running"}


@app.post("/upload")
async def upload_midi(file: UploadFile = File(...)):
    """
    上传 MIDI 文件并返回分析后的音符数据
    """
    try:
        # 保存上传的文件到临时目录
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mid') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        # 使用 pretty_midi 读取 MIDI 文件
        midi_data = pretty_midi.PrettyMIDI(tmp_path)
        
        # 收集所有音符
        all_notes = []
        note_id = 0
        
        for instrument in midi_data.instruments:
            # 跳过打击乐器
            if instrument.is_drum:
                continue
            
            for note in instrument.notes:
                all_notes.append({
                    'id': note_id,
                    'start': float(note.start),
                    'end': float(note.end),
                    'pitch': int(note.pitch),
                    'velocity': int(note.velocity),
                    'is_melody': False  # 默认不是旋律
                })
                note_id += 1
        
        # 应用 Skyline 算法
        all_notes = skyline_algorithm(all_notes)
        
        # 清理临时文件
        os.unlink(tmp_path)
        
        return {
            "duration": float(midi_data.get_end_time()),
            "notes": all_notes
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理 MIDI 文件时出错: {str(e)}")


@app.post("/export")
async def export_midi(request: ExportRequest):
    """
    导出分轨后的 MIDI 文件（旋律 + 原始MIDI）
    """
    try:
        # 创建两个 MIDI 对象
        melody_midi = pretty_midi.PrettyMIDI()
        original_midi = pretty_midi.PrettyMIDI()
        
        # 创建乐器轨道
        melody_instrument = pretty_midi.Instrument(program=0, name="Melody")
        original_instrument = pretty_midi.Instrument(program=0, name="Piano")
        
        # 分配音符到不同轨道
        for note_data in request.notes:
            note = pretty_midi.Note(
                velocity=note_data.velocity,
                pitch=note_data.pitch,
                start=note_data.start,
                end=note_data.end
            )
            
            # 旋律轨道：仅包含标记为旋律的音符
            if note_data.is_melody:
                melody_instrument.notes.append(note)
            
            # 原始轨道：包含所有音符
            original_note = pretty_midi.Note(
                velocity=note_data.velocity,
                pitch=note_data.pitch,
                start=note_data.start,
                end=note_data.end
            )
            original_instrument.notes.append(original_note)
        
        # 添加乐器到 MIDI
        melody_midi.instruments.append(melody_instrument)
        original_midi.instruments.append(original_instrument)
        
        # 创建 ZIP 文件
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 写入旋律 MIDI
            melody_buffer = io.BytesIO()
            melody_midi.write(melody_buffer)
            zip_file.writestr('melody.mid', melody_buffer.getvalue())
            
            # 写入原始 MIDI
            original_buffer = io.BytesIO()
            original_midi.write(original_buffer)
            zip_file.writestr('original.mid', original_buffer.getvalue())
        
        # 重置指针
        zip_buffer.seek(0)
        
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=separated_midi.zip"}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出 MIDI 文件时出错: {str(e)}")


@app.post("/tokenize")
async def tokenize_midi(request: TokenizeRequest):
    """
    将 MIDI 数据转换为训练用 Token 序列
    
    返回格式：
    - source: 仅旋律的token序列
    - target: 完整（旋律+伴奏）的token序列
    - training_sequence: <BOS> [Source] <SEP> [Target] <EOS>
    """
    try:
        # 转换为字典格式
        notes_dict = [note.dict() for note in request.notes]
        
        # 生成 Token
        token_result = midi_to_tokens(
            notes_dict,
            request.duration,
            request.time_quantization
        )
        
        # 统计信息
        melody_count = sum(1 for n in request.notes if n.is_melody)
        accomp_count = len(request.notes) - melody_count
        
        return {
            "source_tokens": token_result["source"],
            "target_tokens": token_result["target"],
            "training_sequence": token_result["training_sequence"],
            "source_length": len(token_result["source"]),
            "target_length": len(token_result["target"]),
            "total_length": len(token_result["training_sequence"]),
            "note_count": len(request.notes),
            "melody_count": melody_count,
            "accompaniment_count": accomp_count,
            "duration": request.duration,
            "time_quantization_ms": request.time_quantization
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token化时出错: {str(e)}")


@app.post("/tokenize_sliced")
async def tokenize_midi_sliced(request: TokenizeSlicedRequest):
    """
    将 MIDI 数据切片并转换为多个训练样本
    
    按固定时间切片（如15秒），生成多个独立的训练序列
    每个序列格式：[1] + Source + [2] + Target + [3]
    
    返回多个样本，适合模型训练
    """
    try:
        # 转换为字典格式
        notes_dict = [note.dict() for note in request.notes]
        
        # 计算切片数量
        slice_duration = request.slice_duration
        overlap = request.overlap
        step = slice_duration - overlap
        num_slices = int(np.ceil((request.duration - overlap) / step))
        
        samples = []
        
        for i in range(num_slices):
            start_time = i * step
            end_time = min(start_time + slice_duration, request.duration)
            
            # 生成该切片的Token
            token_result = midi_to_tokens(
                notes_dict,
                request.duration,
                request.time_quantization,
                start_time,
                end_time
            )
            
            # 只保留有内容的切片
            if len(token_result["source"]) > 0 or len(token_result["target"]) > 0:
                samples.append({
                    "slice_id": i,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": end_time - start_time,
                    "training_sequence": token_result["training_sequence"],
                    "source_length": len(token_result["source"]),
                    "target_length": len(token_result["target"]),
                    "total_length": len(token_result["training_sequence"])
                })
        
        # 统计信息
        melody_count = sum(1 for n in request.notes if n.is_melody)
        accomp_count = len(request.notes) - melody_count
        
        return {
            "samples": samples,
            "num_samples": len(samples),
            "slice_duration": slice_duration,
            "overlap": overlap,
            "total_duration": request.duration,
            "note_count": len(request.notes),
            "melody_count": melody_count,
            "accompaniment_count": accomp_count,
            "time_quantization_ms": request.time_quantization,
            "avg_sample_length": int(np.mean([s["total_length"] for s in samples])) if samples else 0,
            "max_sample_length": max([s["total_length"] for s in samples]) if samples else 0
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"切片Token化时出错: {str(e)}")


@app.post("/json_to_midi")
async def json_to_midi(request: JsonToMidiRequest):
    """
    将精简的 JSON 音符数据转换为 MIDI 文件
    
    接受包含音符列表的JSON，生成标准MIDI文件
    """
    try:
        # 创建 MIDI 对象
        midi = pretty_midi.PrettyMIDI()
        
        # 创建乐器轨道
        instrument = pretty_midi.Instrument(program=0, name="Piano")
        
        # 添加所有音符
        for note_data in request.notes:
            note = pretty_midi.Note(
                velocity=note_data.velocity,
                pitch=note_data.pitch,
                start=note_data.start,
                end=note_data.end
            )
            instrument.notes.append(note)
        
        # 添加乐器到 MIDI
        midi.instruments.append(instrument)
        
        # 写入到内存
        midi_buffer = io.BytesIO()
        midi.write(midi_buffer)
        midi_buffer.seek(0)
        
        return StreamingResponse(
            midi_buffer,
            media_type="audio/midi",
            headers={"Content-Disposition": f"attachment; filename={request.filename}"}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSON转MIDI时出错: {str(e)}")


@app.post("/tokens_to_midi")
async def tokens_to_midi(request: TokensToMidiRequest):
    """
    将Token序列逆转换为MIDI文件
    
    接受training_sequence或任何token序列，逆转换为MIDI
    """
    try:
        # 将tokens转换为音符列表
        notes = tokens_to_notes(request.training_sequence, request.time_quantization)
        
        if not notes:
            raise HTTPException(status_code=400, detail="无法从Token序列中解析出有效音符")
        
        # 创建 MIDI 对象
        midi = pretty_midi.PrettyMIDI()
        
        # 创建乐器轨道
        instrument = pretty_midi.Instrument(program=0, name="Piano")
        
        # 添加所有音符
        for note_data in notes:
            note = pretty_midi.Note(
                velocity=note_data['velocity'],
                pitch=note_data['pitch'],
                start=note_data['start'],
                end=note_data['end']
            )
            instrument.notes.append(note)
        
        # 添加乐器到 MIDI
        midi.instruments.append(instrument)
        
        # 写入到内存
        midi_buffer = io.BytesIO()
        midi.write(midi_buffer)
        midi_buffer.seek(0)
        
        return StreamingResponse(
            midi_buffer,
            media_type="audio/midi",
            headers={"Content-Disposition": f"attachment; filename={request.filename}"}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token转MIDI时出错: {str(e)}")


@app.post("/tokens_to_notes")
async def tokens_to_notes_endpoint(request: TokensToMidiRequest):
    """
    将Token序列转换为音符列表（不生成MIDI文件）
    
    用于前端拼接多个切片时使用
    """
    try:
        # 将tokens转换为音符列表
        notes = tokens_to_notes(request.training_sequence, request.time_quantization)
        
        if not notes:
            raise HTTPException(status_code=400, detail="无法从Token序列中解析出有效音符")
        
        return {
            "notes": notes,
            "count": len(notes)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token解析时出错: {str(e)}")


@app.post("/tokens_to_notes_target_only")
async def tokens_to_notes_target_only(request: TokensToMidiRequest):
    """
    只提取Target部分并转换为音符列表
    
    用于切片合并时只取完整编曲部分，避免Source+Target导致时长翻倍
    
    training_sequence格式: [1] Source [2] Target [3]
    本接口只返回Target部分的音符
    """
    try:
        # 提取Target部分
        target_tokens = extract_target_tokens(request.training_sequence)
        
        if not target_tokens:
            raise HTTPException(status_code=400, detail="无法从训练序列中提取Target部分")
        
        # 转换为音符
        notes = tokens_to_notes(target_tokens, request.time_quantization)
        
        if not notes:
            raise HTTPException(status_code=400, detail="无法从Token序列中解析出有效音符")
        
        return {
            "notes": notes,
            "count": len(notes),
            "target_token_count": len(target_tokens)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token解析时出错: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
