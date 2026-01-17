# MIDI to Token 转换说明

## 概述

本工具支持将 MIDI 音符数据转换为 Token 序列，方便用于机器学习模型训练（如 Transformer、GPT 等）。

## Token 格式

### 1. 复合格式 (Compound)

使用语义化的字符串 Token，便于理解和调试：

```json
[
  "TIME_SHIFT_10",           // 时间前进 10 个量化单位（默认100ms）
  "NOTE_ON_60_80_MELODY",    // 音符开始：音高60，力度80，标记为旋律
  "TIME_SHIFT_5",
  "NOTE_ON_64_75_ACCOMP",    // 音符开始：音高64，力度75，标记为伴奏
  "TIME_SHIFT_3",
  "NOTE_OFF_60_MELODY",      // 音符结束：音高60，旋律
  "NOTE_OFF_64_ACCOMP"       // 音符结束：音高64，伴奏
]
```

**Token 结构说明：**
- `TIME_SHIFT_{n}`: 时间前进 n 个量化单位
- `NOTE_ON_{pitch}_{velocity}_{type}`: 音符按下
  - `pitch`: MIDI 音高 (0-127)
  - `velocity`: 力度 (0-127)
  - `type`: `MELODY` 或 `ACCOMP`
- `NOTE_OFF_{pitch}_{type}`: 音符释放

### 2. 简单格式 (Simple)

使用纯数字序列，更适合模型训练：

```json
[
  0, 10,        // [TIME_SHIFT, delta]
  1, 60, 80, 1, // [NOTE_ON, pitch, velocity, is_melody]
  0, 5,
  1, 64, 75, 0, // [NOTE_ON, pitch, velocity, is_accomp]
  0, 3,
  2, 60, 1,     // [NOTE_OFF, pitch, is_melody]
  2, 64, 0      // [NOTE_OFF, pitch, is_accomp]
]
```

**数字编码：**
- `0`: TIME_SHIFT 事件
- `1`: NOTE_ON 事件
- `2`: NOTE_OFF 事件
- `1/0`: is_melody flag (1=旋律, 0=伴奏)

## 使用方法

### 1. Web 界面

1. 上传 MIDI 文件
2. 修改主旋律标注
3. 点击 "🔤 转Token" 按钮
4. 选择格式（复合/简单）
5. 下载生成的 JSON 文件

### 2. API 调用

```python
import requests

# 准备数据
data = {
    "notes": [
        {
            "id": 0,
            "start": 0.5,
            "end": 1.0,
            "pitch": 60,
            "velocity": 80,
            "is_melody": True
        },
        # ... 更多音符
    ],
    "duration": 120.5,
    "time_quantization": 100,  # 时间量化（毫秒）
    "vocab_type": "compound"   # 或 "simple"
}

# 发送请求
response = requests.post("http://localhost:8000/tokenize", json=data)
result = response.json()

print(f"Token数量: {result['token_count']}")
print(f"Tokens: {result['tokens']}")
```

## 参数配置

### time_quantization

时间量化单位（毫秒）：

- `50`: 高精度，Token 数量多
- `100`: 平衡选择（默认）
- `200`: 低精度，Token 数量少

### vocab_type

Token 格式类型：

- `compound`: 复合格式，适合调试和可视化
- `simple`: 简单数字格式，适合模型训练

## 输出格式

```json
{
  "tokens": [...],              // Token 序列
  "token_count": 1234,          // Token 总数
  "note_count": 456,            // 音符总数
  "melody_count": 123,          // 旋律音符数
  "accompaniment_count": 333,   // 伴奏音符数
  "duration": 120.5,            // 总时长（秒）
  "vocab_type": "compound",     // Token 类型
  "time_quantization_ms": 100   // 时间量化单位
}
```

## 用于机器学习

### 1. 构建词汇表 (Vocabulary)

**复合格式：**
```python
# 收集所有唯一的 Token
vocab = set()
for token in tokens:
    vocab.add(token)

# 创建 token -> id 映射
token_to_id = {token: i for i, token in enumerate(sorted(vocab))}
id_to_token = {i: token for token, i in token_to_id.items()}
```

**简单格式：**
```python
# 固定的词汇表
vocab = {
    0: "TIME_SHIFT",
    1: "NOTE_ON", 
    2: "NOTE_OFF",
    # 音高 0-127
    # 力度 0-127
    # 标记 0-1
}
```

### 2. 序列处理

```python
# 切分为固定长度的序列
def chunk_tokens(tokens, chunk_size=512, overlap=64):
    chunks = []
    for i in range(0, len(tokens), chunk_size - overlap):
        chunk = tokens[i:i + chunk_size]
        if len(chunk) == chunk_size:
            chunks.append(chunk)
    return chunks
```

### 3. 数据增强

```python
# 音高转置
def transpose(tokens, semitones):
    # 实现音高偏移
    pass

# 速度变化
def time_stretch(tokens, factor):
    # 修改 TIME_SHIFT 值
    pass
```

## 示例应用

### 1. 旋律生成模型

训练一个只生成旋律的 Transformer 模型：

```python
# 只使用 is_melody=True 的音符
melody_tokens = [t for t in tokens if "MELODY" in t or isinstance(t, int)]
```

### 2. 伴奏生成模型

给定旋律，生成伴奏：

```python
# 输入：旋律 tokens
# 输出：伴奏 tokens
model.generate(melody_tokens) -> accompaniment_tokens
```

### 3. 主旋律识别模型

训练模型预测哪些音符是主旋律：

```python
# 输入：所有音符
# 输出：每个音符的 is_melody 标签
```

## 高级配置

### 自定义时间量化

```python
# 使用不同的量化精度
result_fine = tokenize(notes, time_quantization=50)   # 50ms
result_coarse = tokenize(notes, time_quantization=200) # 200ms
```

### 添加额外信息

可以扩展 Token 格式包含更多信息：

- 乐器类型
- 音符时值（四分音符、八分音符等）
- 和弦标注
- 小节线标记

## 性能优化

- **批量处理**: 一次处理多个 MIDI 文件
- **并行化**: 使用多进程加速转换
- **缓存**: 缓存已转换的结果

## 常见问题

**Q: Token 数量过多怎么办？**  
A: 增加 time_quantization 值，或只保留旋律部分

**Q: 如何还原为 MIDI？**  
A: 反向解析 Token 序列，重建音符事件

**Q: 简单格式和复合格式哪个更好？**  
A: 简单格式更适合模型训练，复合格式更便于调试

## 参考资料

- [MIDI Specification](https://www.midi.org/specifications)
- [Music Transformer Paper](https://arxiv.org/abs/1809.04281)
- [MuseNet](https://openai.com/research/musenet)
