# Token 转 MIDI 功能说明

## 新功能概述

### 1. Token 序列可逆转换为 MIDI

现在可以将训练用的 Token 序列逆转换回 MIDI 文件，实现完整的双向转换：

```
MIDI → Tokens → MIDI
```

### 2. 导出文件名使用原始文件名

导出的压缩包现在会自动使用上传的 MIDI 文件名进行命名：
- 上传文件：`my_song.mid`
- 导出文件：`my_song_separated.zip`

## 使用方法

### Token → MIDI 转换

#### 前端操作
1. 点击 **"🔄 Token→MIDI"** 按钮
2. 选择包含 Token 序列的 JSON 文件
3. 系统自动识别格式并转换

#### 支持的 JSON 格式

**格式 1：单一训练序列**
```json
{
  "training_sequence": [1, 10, 60, 0, 4, 11, 60, 2, 20, 48, ...],
  "time_quantization_ms": 100
}
```

**格式 2：切片样本集合**（如 `tokens_sliced.json`）
```json
{
  "samples": [
    {
      "slice_id": 0,
      "training_sequence": [1, 10, 62, 0, 2, 11, 62, ...],
      "start_time": 0,
      "end_time": 8
    },
    ...
  ],
  "time_quantization_ms": 100
}
```

对于切片格式，系统会提示选择要转换的样本编号。

### Token 编码说明

Token 序列使用纯数字格式：

| Token | 含义 |
|-------|------|
| `1` | `<BOS>` - 序列开始 |
| `2` | `<SEP>` - Source/Target 分隔符 |
| `3` | `<EOS>` - 序列结束 |
| `0, time_delta` | TIME 事件（时间增量，单位：量化步长） |
| `10, pitch` | NOTE_ON（旋律） |
| `11, pitch` | NOTE_OFF（旋律） |
| `20, pitch` | NOTE_ON（伴奏） |
| `21, pitch` | NOTE_OFF（伴奏） |

### 序列结构

完整的训练序列结构：
```
[1] + Source + [2] + Target + [3]
```

- **Source**: 仅包含旋律音符的 Token 序列
- **Target**: 包含所有音符（旋律 + 伴奏）的 Token 序列

## API 接口

### POST `/tokens_to_midi`

将 Token 序列转换为 MIDI 文件。

**请求体：**
```json
{
  "training_sequence": [1, 10, 60, 0, 4, 11, 60, 2, 3],
  "time_quantization": 100,
  "filename": "output.mid"
}
```

**响应：**
- Content-Type: `audio/midi`
- 返回 MIDI 文件二进制数据

### POST `/json_to_midi`

将音符列表 JSON 转换为 MIDI 文件（保持不变）。

**请求体：**
```json
{
  "notes": [
    {"pitch": 60, "start": 0.0, "end": 0.5, "velocity": 80, "is_melody": true},
    ...
  ],
  "filename": "output.mid"
}
```

## 技术实现

### 后端实现（`backend/main.py`）

#### 新增函数
- **`tokens_to_notes()`**: Token 序列解析为音符列表
  - 支持旋律/伴奏分离标记
  - 时间量化解析
  - 完整的 NOTE_ON/NOTE_OFF 配对

#### 新增数据模型
```python
class TokensToMidiRequest(BaseModel):
    training_sequence: List[int]
    time_quantization: int = 100
    filename: str = "output.mid"
```

### 前端实现（`frontend/src/App.vue`）

#### 新增状态
```javascript
const originalFilename = ref('')  // 保存原始文件名
```

#### 新增函数
- **`handleTokensUpload()`**: 处理 Token JSON 上传
  - 自动识别单一序列/切片集合格式
  - 对于切片格式，提示用户选择样本
  - 调用 `/tokens_to_midi` API

#### 修改函数
- **`handleFileUpload()`**: 保存原始文件名（去除扩展名）
- **`exportMidi()`**: 使用原始文件名生成导出文件名

## 测试示例

### 简单测试
```python
from main import tokens_to_notes

test_tokens = [
    1,        # BOS
    10, 60,   # Melody C4 ON
    0, 4,     # TIME 400ms
    11, 60,   # Melody C4 OFF
    2,        # SEP
    10, 60,   # Melody C4 ON
    20, 48,   # Accomp C3 ON
    0, 4,     # TIME 400ms
    11, 60,   # Melody C4 OFF
    21, 48,   # Accomp C3 OFF
    3         # EOS
]

notes = tokens_to_notes(test_tokens, time_quantization=100)
print(f"Parsed {len(notes)} notes")
# Output: Parsed 3 notes
```

### 切片数据测试
已验证可以成功转换 `tokens_sliced.json` 中的所有样本。

## 优势与应用

1. **完整的双向转换**：支持 MIDI ↔ Token 的完整转换循环
2. **训练数据验证**：可以将生成的 Token 转回 MIDI 进行听觉验证
3. **模型输出转换**：可以将训练好的模型输出转换为可播放的 MIDI
4. **切片数据支持**：支持单独转换任意切片样本
5. **文件名保持**：导出文件保留原始文件名，便于管理

## 注意事项

1. Token 序列必须遵循正确的编码格式
2. NOTE_ON 和 NOTE_OFF 必须正确配对
3. 时间量化参数必须与生成 Token 时保持一致
4. 对于切片数据，每个样本独立转换，不会自动合并

## 更新日志

### 2026-01-18
- ✅ 新增 `tokens_to_notes()` 函数实现 Token → 音符转换
- ✅ 新增 `/tokens_to_midi` API 端点
- ✅ 前端新增 "🔄 Token→MIDI" 上传按钮
- ✅ 前端新增 `handleTokensUpload()` 函数处理 Token 上传
- ✅ 修改导出功能，使用原始文件名命名压缩包
- ✅ 支持单一序列和切片集合两种 JSON 格式
- ✅ 完整测试验证功能正常
