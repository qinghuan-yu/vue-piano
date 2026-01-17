"""
Animenz-Melody-Annotator Backend
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

app = FastAPI(title="Animenz Melody Annotator API")

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
    time_quantization: int = 100  # 时间量化单位（毫秒）
    vocab_type: str = "compound"  # compound: 复合token, simple: 简单token


def midi_to_tokens(notes: List[Dict], duration: float, time_quantization: int = 100, vocab_type: str = "compound") -> List:
    """
    将 MIDI 音符转换为 Token 序列
    
    支持两种 Token 化方式：
    1. compound: 复合 token，格式如 [TIME_50, NOTE_ON_60_80, NOTE_OFF_60, ...]
    2. simple: 简单 token，格式如 [50, 1, 60, 80, 2, 60, ...]
    
    Args:
        notes: 音符列表
        duration: MIDI 总时长
        time_quantization: 时间量化单位（毫秒）
        vocab_type: Token 类型
    
    Returns:
        Token 序列
    """
    # 创建事件列表：(时间, 事件类型, 音高, 力度, 是否旋律)
    events = []
    
    for note in notes:
        # NOTE_ON 事件
        events.append({
            'time': note['start'],
            'type': 'note_on',
            'pitch': note['pitch'],
            'velocity': note['velocity'],
            'is_melody': note['is_melody']
        })
        # NOTE_OFF 事件
        events.append({
            'time': note['end'],
            'type': 'note_off',
            'pitch': note['pitch'],
            'velocity': 0,
            'is_melody': note['is_melody']
        })
    
    # 按时间排序
    events.sort(key=lambda x: (x['time'], x['type'] == 'note_off'))
    
    # 转换为 Token
    tokens = []
    current_time = 0
    
    if vocab_type == "compound":
        # 复合 Token 方式
        for event in events:
            # 计算时间差（量化）
            time_delta = int((event['time'] - current_time) * 1000 / time_quantization)
            
            if time_delta > 0:
                tokens.append(f"TIME_SHIFT_{time_delta}")
                current_time = event['time']
            
            # 音符事件
            melody_tag = "_MELODY" if event['is_melody'] else "_ACCOMP"
            if event['type'] == 'note_on':
                tokens.append(f"NOTE_ON_{event['pitch']}_{event['velocity']}{melody_tag}")
            else:
                tokens.append(f"NOTE_OFF_{event['pitch']}{melody_tag}")
    
    elif vocab_type == "simple":
        # 简单 Token 方式（数字序列）
        for event in events:
            # 时间差（量化）
            time_delta = int((event['time'] - current_time) * 1000 / time_quantization)
            
            if time_delta > 0:
                tokens.extend([0, time_delta])  # 0 = TIME_SHIFT
                current_time = event['time']
            
            # 音符事件
            melody_flag = 1 if event['is_melody'] else 0
            if event['type'] == 'note_on':
                tokens.extend([1, event['pitch'], event['velocity'], melody_flag])  # 1 = NOTE_ON
            else:
                tokens.extend([2, event['pitch'], melody_flag])  # 2 = NOTE_OFF
    
    return tokens


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
    return {"message": "Animenz Melody Annotator API is running"}


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
    导出分轨后的 MIDI 文件（旋律 + 伴奏）
    """
    try:
        # 创建两个 MIDI 对象
        melody_midi = pretty_midi.PrettyMIDI()
        accompaniment_midi = pretty_midi.PrettyMIDI()
        
        # 创建乐器轨道
        melody_instrument = pretty_midi.Instrument(program=0, name="Melody")
        accompaniment_instrument = pretty_midi.Instrument(program=0, name="Accompaniment")
        
        # 分配音符到不同轨道
        for note_data in request.notes:
            note = pretty_midi.Note(
                velocity=note_data.velocity,
                pitch=note_data.pitch,
                start=note_data.start,
                end=note_data.end
            )
            
            if note_data.is_melody:
                melody_instrument.notes.append(note)
            else:
                accompaniment_instrument.notes.append(note)
        
        # 添加乐器到 MIDI
        melody_midi.instruments.append(melody_instrument)
        accompaniment_midi.instruments.append(accompaniment_instrument)
        
        # 创建 ZIP 文件
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 写入旋律 MIDI
            melody_buffer = io.BytesIO()
            melody_midi.write(melody_buffer)
            zip_file.writestr('melody.mid', melody_buffer.getvalue())
            
            # 写入伴奏 MIDI
            accompaniment_buffer = io.BytesIO()
            accompaniment_midi.write(accompaniment_buffer)
            zip_file.writestr('accompaniment.mid', accompaniment_buffer.getvalue())
        
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
    将 MIDI 数据转换为 Token 序列
    
    支持两种格式：
    - compound: 复合token (如 "TIME_SHIFT_10", "NOTE_ON_60_80_MELODY")
    - simple: 简单数字序列 (如 [0, 10, 1, 60, 80, 1])
    """
    try:
        # 转换为字典格式
        notes_dict = [note.dict() for note in request.notes]
        
        # 生成 Token
        tokens = midi_to_tokens(
            notes_dict,
            request.duration,
            request.time_quantization,
            request.vocab_type
        )
        
        # 统计信息
        melody_count = sum(1 for n in request.notes if n.is_melody)
        accomp_count = len(request.notes) - melody_count
        
        return {
            "tokens": tokens,
            "token_count": len(tokens),
            "note_count": len(request.notes),
            "melody_count": melody_count,
            "accompaniment_count": accomp_count,
            "duration": request.duration,
            "vocab_type": request.vocab_type,
            "time_quantization_ms": request.time_quantization
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token化时出错: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
