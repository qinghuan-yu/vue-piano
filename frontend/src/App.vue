<template>
  <div class="app-container">
    <!-- 顶部控制栏 -->
    <header class="control-bar">
      <div class="logo">
        <h1>🎹 Melody Annotator</h1>
      </div>
      
      <div class="controls">
        <!-- 上传按钮 -->
        <label class="btn btn-primary">
          <input 
            type="file" 
            accept=".mid,.midi" 
            @change="handleFileUpload"
            style="display: none"
          />
          📁 上传 MIDI
        </label>
        
        <!-- 播放控制 -->
        <button 
          class="btn btn-success" 
          @click="togglePlay"
          :disabled="!midiData"
        >
          {{ isPlaying ? '⏸ 暂停' : '▶ 播放' }}
        </button>
        
        <!-- 速度控制 -->
        <div class="speed-control" v-if="midiData">
          <button 
            class="btn btn-small" 
            @click="changeSpeed(-0.25)"
            :disabled="playbackSpeed <= 0.25"
          >
            −
          </button>
          <span class="speed-display">{{ playbackSpeed.toFixed(2) }}x</span>
          <button 
            class="btn btn-small" 
            @click="changeSpeed(0.25)"
            :disabled="playbackSpeed >= 2.0"
          >
            +
          </button>
        </div>
        
        <!-- Solo 模式 -->
        <button 
          class="btn btn-toggle" 
          :class="{ active: soloMode }"
          @click="soloMode = !soloMode"
          :disabled="!midiData"
        >
          {{ soloMode ? '🎵' : '🎹' }} Solo {{ soloMode ? 'ON' : 'OFF' }}
        </button>
        
        <!-- 导出按钮 -->
        <button 
          class="btn btn-accent" 
          @click="exportMidi"
          :disabled="!midiData"
        >
          💾 导出分轨
        </button>
        
        <!-- Token化按钮 -->
        <button 
          class="btn btn-warning" 
          @click="tokenizeMidi"
          :disabled="!midiData"
        >
          🔤 转Token
        </button>
        
        <!-- 切片Token化按钮 -->
        <button 
          class="btn btn-success" 
          @click="tokenizeMidiSliced"
          :disabled="!midiData"
        >
          ✂️ 切片Token
        </button>
        
        <!-- JSON转MIDI按钮 -->
        <label class="btn btn-info">
          <input 
            type="file" 
            accept=".json" 
            @change="handleJsonUpload"
            style="display: none"
          />
          📤 JSON→MIDI
        </label>
        
        <!-- Token转MIDI按钮 -->
        <label class="btn btn-info">
          <input 
            type="file" 
            accept=".json" 
            @change="handleTokensUpload"
            style="display: none"
          />
          🔄 Token→MIDI
        </label>
        
        <!-- 统计信息 -->
        <div class="stats" v-if="midiData">
          <span class="stat-item melody">旋律: {{ melodyCount }}</span>
          <span class="stat-item accomp">伴奏: {{ accompCount }}</span>
          <span class="stat-item total">总计: {{ totalNotes }}</span>
        </div>
      </div>
    </header>
    
    <!-- 播放进度条 -->
    <div class="progress-bar-container" v-if="midiData">
      <div class="progress-time">{{ formatTime(currentTime) }}</div>
      <div class="progress-bar" @click="seekTo">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
        <div class="progress-handle" :style="{ left: progressPercent + '%' }"></div>
      </div>
      <div class="progress-time">{{ formatTime(midiData.duration) }}</div>
    </div>
    
    <!-- 主视图区域 -->
    <main class="main-content">
      <div v-if="!midiData" class="empty-state">
        <div class="empty-icon">🎼</div>
        <h2>欢迎使用 Melody Annotator</h2>
        <p>请上传一个 MIDI 文件开始标注主旋律</p>
        <label class="btn btn-primary btn-large">
          <input 
            type="file" 
            accept=".mid,.midi" 
            @change="handleFileUpload"
            style="display: none"
          />
          选择 MIDI 文件
        </label>
      </div>
      
      <PianoRoll 
        ref="pianoRollRef"
        v-else
        :notes="midiData.notes"
        :duration="midiData.duration"
        :current-time="currentTime"
        :is-playing="isPlaying"
        @update:notes="handleNotesUpdate"
        @play-note="playNote"
      />
    </main>
    
    <!-- 加载提示 -->
    <div v-if="isLoading" class="loading-overlay">
      <div class="spinner"></div>
      <p>{{ loadingText }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import * as Tone from 'tone'
import PianoRoll from './components/PianoRoll.vue'

// 状态管理
const midiData = ref(null)
const originalFilename = ref('')
const isLoading = ref(false)
const loadingText = ref('处理中...')
const isPlaying = ref(false)
const soloMode = ref(false)
const playbackSpeed = ref(1.0)
const currentTime = ref(0)
const pausedTime = ref(0)

// API 基础路径
const API_BASE = '/api'

// 计算属性：统计信息
const melodyCount = computed(() => {
  if (!midiData.value) return 0
  return midiData.value.notes.filter(n => n.is_melody).length
})

const accompCount = computed(() => {
  if (!midiData.value) return 0
  return midiData.value.notes.filter(n => !n.is_melody).length
})

const totalNotes = computed(() => {
  if (!midiData.value) return 0
  return midiData.value.notes.length
})

// Tone.js 播放器
let synth = null
let scheduledNotes = []
let progressInterval = null
let startTime = 0

// PianoRoll 组件引用
const pianoRollRef = ref(null)

// 计算属性：播放进度百分比
const progressPercent = computed(() => {
  if (!midiData.value || !midiData.value.duration) return 0
  return (currentTime.value / midiData.value.duration) * 100
})

// 格式化时间显示
const formatTime = (seconds) => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

/**
 * 初始化音频合成器
 */
const initSynth = () => {
  if (!synth) {
    synth = new Tone.PolySynth(Tone.Synth, {
      oscillator: { type: 'triangle' },
      envelope: {
        attack: 0.005,
        decay: 0.1,
        sustain: 0.3,
        release: 0.8
      }
    }).toDestination()
  }
}

/**
 * 处理文件上传
 */
const handleFileUpload = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  
  // 保存原始文件名（去掉扩展名）
  originalFilename.value = file.name.replace(/\.[^/.]+$/, '')
  
  isLoading.value = true
  loadingText.value = '正在分析 MIDI 文件...'
  
  try {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await axios.post(`${API_BASE}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    midiData.value = response.data
  } catch (error) {
    console.error('上传失败:', error)
    alert('上传失败：' + (error.response?.data?.detail || error.message))
  } finally {
    isLoading.value = false
    event.target.value = '' // 重置文件输入
  }
}

/**
 * 处理JSON文件上传并转换为MIDI
 */
const handleJsonUpload = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  
  isLoading.value = true
  loadingText.value = '正在转换 JSON 为 MIDI...'
  
  try {
    // 读取JSON文件
    const fileContent = await file.text()
    const jsonData = JSON.parse(fileContent)
    
    // 确保数据格式正确
    const requestData = {
      notes: jsonData.notes || [],
      filename: jsonData.filename || 'converted.mid'
    }
    
    // 发送到后端转换
    const response = await axios.post(`${API_BASE}/json_to_midi`, requestData, {
      responseType: 'blob'
    })
    
    // 下载生成的MIDI文件
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = requestData.filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    
    alert('✅ JSON 已成功转换为 MIDI 文件')
  } catch (error) {
    console.error('JSON转换失败:', error)
    alert('JSON转换失败：' + (error.response?.data?.detail || error.message || '请检查JSON格式'))
  } finally {
    isLoading.value = false
    event.target.value = '' // 重置文件输入
  }
}

/**
 * 处理Token JSON文件上传并转换为MIDI
 */
const handleTokensUpload = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  
  isLoading.value = true
  loadingText.value = '正在将 Token 转换为 MIDI...'
  
  try {
    // 读取JSON文件
    const fileContent = await file.text()
    const jsonData = JSON.parse(fileContent)
    
    // 检查是否是切片Token格式
    let notesData = []
    let filename
    
    if (jsonData.samples && Array.isArray(jsonData.samples)) {
      // 切片Token格式 - 询问用户是否拼接所有切片
      if (jsonData.samples.length === 0) {
        throw new Error('没有找到可用的训练样本')
      }
      
      const shouldMerge = jsonData.samples.length > 1 && 
        confirm(`找到 ${jsonData.samples.length} 个样本切片。\n\n点击"确定"将所有切片拼接为完整MIDI\n点击"取消"仅转换单个切片`)
      
      if (shouldMerge) {
        // 拼接所有切片
        isLoading.value = true
        loadingText.value = `正在拼接 ${jsonData.samples.length} 个切片...`
        
        // 收集所有切片的音符，并调整时间
        for (const sample of jsonData.samples) {
          // 使用target_only接口，只提取Target部分（完整编曲）
          // 避免Source+Target导致时长翻倍
          const response = await axios.post(`${API_BASE}/tokens_to_notes_target_only`, {
            training_sequence: sample.training_sequence,
            time_quantization: jsonData.time_quantization_ms || 10
          })
          
          // 调整音符时间：加上切片起始时间（绝对时间偏移）
          const adjustedNotes = response.data.notes.map(note => ({
            ...note,
            start: note.start + sample.start_time,
            end: note.end + sample.start_time
          }))
          
          notesData.push(...adjustedNotes)
        }
        
        filename = 'merged_all_slices.mid'
      } else {
        // 转换单个切片
        const sampleIndex = jsonData.samples.length === 1 ? 0 : 
          parseInt(prompt(`请输入要转换的样本编号 (0-${jsonData.samples.length - 1})：`, '0'))
        
        if (isNaN(sampleIndex) || sampleIndex < 0 || sampleIndex >= jsonData.samples.length) {
          alert('无效的样本编号')
          return
        }
        
        const response = await axios.post(`${API_BASE}/tokens_to_notes`, {
          training_sequence: jsonData.samples[sampleIndex].training_sequence,
          time_quantization: jsonData.time_quantization_ms || 10
        })
        
        notesData = response.data.notes
        filename = `sample_${sampleIndex}.mid`
      }
    } else if (jsonData.training_sequence) {
      // 单一Token格式
      const response = await axios.post(`${API_BASE}/tokens_to_notes`, {
        training_sequence: jsonData.training_sequence,
        time_quantization: jsonData.time_quantization_ms || 10
      })
      
      notesData = response.data.notes
      filename = 'converted.mid'
    } else {
      throw new Error('无法识别的Token格式，请确保JSON包含 training_sequence 或 samples 字段')
    }
    
    // 使用音符数据生成MIDI
    const response = await axios.post(`${API_BASE}/json_to_midi`, {
      notes: notesData,
      filename: filename
    }, {
      responseType: 'blob'
    })
    
    // 下载生成的MIDI文件
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    
    alert('✅ Token 已成功转换为 MIDI 文件')
  } catch (error) {
    console.error('Token转换失败:', error)
    alert('Token转换失败：' + (error.response?.data?.detail || error.message || '请检查Token格式'))
  } finally {
    isLoading.value = false
    event.target.value = '' // 重置文件输入
  }
}

/**
 * 更新音符数据
 */
const handleNotesUpdate = (updatedNotes) => {
  if (midiData.value) {
    midiData.value.notes = updatedNotes
  }
}

/**
 * 播放/暂停切换
 */
const togglePlay = async () => {
  if (!midiData.value) return
  
  if (isPlaying.value) {
    // 停止播放
    stopPlayback()
  } else {
    // 开始播放
    await startPlayback()
  }
}

/**
 * 开始播放
 */
const startPlayback = async () => {
  try {
    await Tone.start()
    initSynth()
    
    isPlaying.value = true
    startTime = Tone.now()
    const resumeFrom = pausedTime.value
    
    // 筛选要播放的音符
    const notesToPlay = soloMode.value 
      ? midiData.value.notes.filter(n => n.is_melody)
      : midiData.value.notes
    
    // 直接调度所有音符（不使用Transport）
    let scheduledCount = 0
    notesToPlay.forEach(note => {
      if (note.end > resumeFrom) {
        const midiNote = Tone.Frequency(note.pitch, 'midi').toNote()
        const duration = (note.end - note.start) / playbackSpeed.value
        const velocity = note.velocity / 127
        const scheduleTime = Math.max(0, note.start - resumeFrom) / playbackSpeed.value
        const absoluteTime = Tone.now() + scheduleTime
        
        // 直接使用 Tone.Draw.schedule 调度
        const eventId = Tone.Transport.scheduleOnce(() => {
          synth.triggerAttackRelease(midiNote, duration, Tone.now(), velocity)
        }, `+${scheduleTime}`)
        
        scheduledNotes.push(eventId)
        scheduledCount++
      }
    })
    
    // 播放完成后停止
    const remainingDuration = (midiData.value.duration - resumeFrom) / playbackSpeed.value
    Tone.Transport.scheduleOnce(() => {
      stopPlayback(true)
    }, `+${remainingDuration}`)
    
    // 启动进度更新
    progressInterval = setInterval(() => {
      currentTime.value = resumeFrom + (Tone.now() - startTime) * playbackSpeed.value
      if (currentTime.value >= midiData.value.duration) {
        currentTime.value = midiData.value.duration
      }
    }, 50)
    
    Tone.Transport.start()
  } catch (error) {
    console.error('播放错误:', error)
    isPlaying.value = false
  }
}

/**
 * 停止播放
 */
const stopPlayback = (isComplete = false) => {
  isPlaying.value = false
  
  // 清除进度更新定时器
  if (progressInterval) {
    clearInterval(progressInterval)
    progressInterval = null
  }
  
  // 记录暂停位置
  if (!isComplete) {
    pausedTime.value = currentTime.value
  } else {
    // 播放完成，重置到开头
    pausedTime.value = 0
    currentTime.value = 0
  }
  
  Tone.Transport.stop()
  Tone.Transport.cancel()
  scheduledNotes = []
  
  // 释放所有正在播放的音符
  if (synth) {
    synth.releaseAll()
  }
}

/**
 * 改变播放速度
 */
const changeSpeed = (delta) => {
  playbackSpeed.value = Math.max(0.25, Math.min(2.0, playbackSpeed.value + delta))
  
  // 如果正在播放，需要重新开始
  if (isPlaying.value) {
    stopPlayback()
    startPlayback()
  }
}

/**
 * 播放单个音符（供PianoRoll组件调用）
 */
const playNote = (pitch, velocity = 80, duration = 0.3) => {
  initSynth()
  const midiNote = Tone.Frequency(pitch, 'midi').toNote()
  const vel = velocity / 127
  synth.triggerAttackRelease(midiNote, duration, Tone.now(), vel)
}

/**
 * 点击进度条跳转
 */
const seekTo = (event) => {
  if (!midiData.value) return
  
  const rect = event.currentTarget.getBoundingClientRect()
  const percent = (event.clientX - rect.left) / rect.width
  const newTime = percent * midiData.value.duration
  
  currentTime.value = newTime
  pausedTime.value = newTime
  
  // 同步滚动钢琴卷帘视图
  if (pianoRollRef.value) {
    pianoRollRef.value.scrollToTime(newTime)
  }
  
  // 如果正在播放，重新开始
  if (isPlaying.value) {
    stopPlayback()
    startPlayback()
  }
}

/**
 * 导出 MIDI 文件
 */
const exportMidi = async () => {
  if (!midiData.value) return
  
  isLoading.value = true
  loadingText.value = '正在生成 MIDI 文件...'
  
  try {
    const response = await axios.post(`${API_BASE}/export`, {
      notes: midiData.value.notes,
      duration: midiData.value.duration
    }, {
      responseType: 'blob'
    })
    
    // 使用原始文件名或默认名称
    const filename = originalFilename.value ? `${originalFilename.value}_separated.zip` : 'separated_midi.zip'
    
    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch (error) {
    console.error('导出失败:', error)
    alert('导出失败：' + (error.response?.data?.detail || error.message))
  } finally {
    isLoading.value = false
  }
}

/**
 * Token化 MIDI 数据
 */
const tokenizeMidi = async () => {
  if (!midiData.value) return
  
  isLoading.value = true
  loadingText.value = '正在转换为 Token...'
  
  try {
    const response = await axios.post(`${API_BASE}/tokenize`, {
      notes: midiData.value.notes,
      duration: midiData.value.duration,
      time_quantization: 10  // 10ms 量化 - 提高精度保留快速音符
    })
    
    const result = response.data
    
    // 创建下载文件
    const tokenData = JSON.stringify(result, null, 2)
    const blob = new Blob([tokenData], { type: 'application/json' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'tokens.json')
    document.body.appendChild(link)
    link.click()
    link.remove()
    
    // 显示统计信息
    alert(`✅ Token化完成!\n\n` +
      `训练序列长度: ${result.total_length}\n` +
      `Source长度 (仅旋律): ${result.source_length}\n` +
      `Target长度 (完整): ${result.target_length}\n` +
      `音符数量: ${result.note_count}\n` +
      `旋律音符: ${result.melody_count}\n` +
      `伴奏音符: ${result.accompaniment_count}\n` +
      `时长: ${result.duration.toFixed(2)}秒\n\n` +
      `Token编码:\n` +
      `1=<BOS>, 2=<SEP>, 3=<EOS>\n` +
      `0,time=TIME事件\n` +
      `10,pitch=NOTE_ON(旋律)\n` +
      `11,pitch=NOTE_OFF(旋律)\n` +
      `20,pitch=NOTE_ON(伴奏)\n` +
      `21,pitch=NOTE_OFF(伴奏)`)
    
  } catch (error) {
    console.error('Token化失败:', error)
    alert('Token化失败：' + (error.response?.data?.detail || error.message))
  } finally {
    isLoading.value = false
  }
}

/**
 * 切片Token化 MIDI 数据
 */
const tokenizeMidiSliced = async () => {
  if (!midiData.value) return
  
  // 让用户选择切片时长
  const sliceDuration = prompt('请输入每个切片的时长（秒）：', '8')
  if (!sliceDuration) return
  
  const duration = parseFloat(sliceDuration)
  if (isNaN(duration) || duration <= 0) {
    alert('无效的时长值')
    return
  }
  
  isLoading.value = true
  loadingText.value = '正在切片并转换为 Token...'
  
  try {
    const response = await axios.post(`${API_BASE}/tokenize_sliced`, {
      notes: midiData.value.notes,
      duration: midiData.value.duration,
      time_quantization: 10,  // 10ms精度  // 100ms 量化
      slice_duration: duration,
      overlap: 0  // 无重叠
    })
    
    const result = response.data
    
    // 创建下载文件
    const tokenData = JSON.stringify(result, null, 2)
    const blob = new Blob([tokenData], { type: 'application/json' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'tokens_sliced.json')
    document.body.appendChild(link)
    link.click()
    link.remove()
    
    // 显示统计信息
    alert(`✅ 切片Token化完成!

` +
      `生成样本数: ${result.num_samples}
` +
      `切片时长: ${result.slice_duration}秒
` +
      `总时长: ${result.total_duration.toFixed(2)}秒
` +
      `平均样本长度: ${result.avg_sample_length} tokens
` +
      `最大样本长度: ${result.max_sample_length} tokens
` +
      `音符数量: ${result.note_count}
` +
      `旋律音符: ${result.melody_count}
` +
      `伴奏音符: ${result.accompaniment_count}

` +
      `Token编码:
` +
      `1=<BOS>, 2=<SEP>, 3=<EOS>
` +
      `0,time=TIME事件
` +
      `10,pitch=NOTE_ON(旋律)
` +
      `11,pitch=NOTE_OFF(旋律)
` +
      `20,pitch=NOTE_ON(伴奏)
` +
      `21,pitch=NOTE_OFF(伴奏)

` +
      `已保存到: tokens_sliced.json`)
    
  } catch (error) {
    console.error('切片Token化失败:', error)
    alert('切片Token化失败：' + (error.response?.data?.detail || error.message))
  } finally {
    isLoading.value = false
  }
}

// 监听 Solo Mode 切换
watch(soloMode, (newValue, oldValue) => {
  // 如果正在播放，重新开始以应用新的模式
  if (isPlaying.value) {
    stopPlayback(false)
    startPlayback()
  }
})

// 键盘快捷键：空格键切换播放/暂停
const handleKeyPress = (event) => {
  // 空格键切换播放状态
  if (event.code === 'Space' && midiData.value) {
    event.preventDefault() // 阻止页面滚动
    togglePlay()
  }
}

// 生命周期：添加和移除键盘监听
onMounted(() => {
  window.addEventListener('keydown', handleKeyPress)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyPress)
})
</script>

<style scoped>
.app-container {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0f172a;
}

.control-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: #1e293b;
  border-bottom: 2px solid #334155;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  flex-shrink: 0;
}

.logo h1 {
  font-size: 20px;
  font-weight: 600;
  color: #f1f5f9;
  margin: 0;
}

.controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #3b82f6;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-success {
  background: #10b981;
  color: white;
}

.btn-success:hover:not(:disabled) {
  background: #059669;
}

.btn-accent {
  background: #8b5cf6;
  color: white;
}

.btn-accent:hover:not(:disabled) {
  background: #7c3aed;
}

.btn-warning {
  background: #f59e0b;
  color: white;
}

.btn-warning:hover:not(:disabled) {
  background: #d97706;
}

.btn-info {
  background: #0ea5e9;
  color: white;
}

.btn-info:hover:not(:disabled) {
  background: #0284c7;
}

.btn-large {
  padding: 12px 24px;
  font-size: 16px;
}

.btn-small {
  padding: 4px 10px;
  font-size: 16px;
  background: #475569;
  color: white;
  font-weight: 600;
}

.btn-small:hover:not(:disabled) {
  background: #64748b;
}

.btn-toggle {
  background: #475569;
  color: #cbd5e1;
}

.btn-toggle:hover:not(:disabled) {
  background: #64748b;
}

.btn-toggle.active {
  background: #10b981;
  color: white;
}

.btn-toggle.active:hover:not(:disabled) {
  background: #059669;
}

.speed-control {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  background: rgba(51, 65, 85, 0.5);
  border-radius: 6px;
}

.speed-display {
  font-size: 13px;
  font-weight: 600;
  color: #fbbf24;
  min-width: 48px;
  text-align: center;
}

.stats {
  display: flex;
  gap: 12px;
  padding-left: 12px;
  border-left: 2px solid #334155;
}

.stat-item {
  font-size: 13px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
}

.stat-item.melody {
  background: rgba(74, 222, 128, 0.2);
  color: #4ade80;
}

.stat-item.accomp {
  background: rgba(75, 85, 99, 0.3);
  color: #9ca3af;
}

.stat-item.total {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
}

.progress-bar-container {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 24px;
  background: #1e293b;
  border-bottom: 1px solid #334155;
  flex-shrink: 0;
}

.progress-time {
  font-size: 12px;
  font-weight: 500;
  color: #94a3b8;
  min-width: 45px;
  text-align: center;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: #334155;
  border-radius: 3px;
  position: relative;
  cursor: pointer;
  transition: height 0.2s;
}

.progress-bar:hover {
  height: 8px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  border-radius: 3px;
  transition: width 0.1s linear;
}

.progress-handle {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 14px;
  height: 14px;
  background: #ffffff;
  border: 2px solid #3b82f6;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
  opacity: 0;
  transition: opacity 0.2s;
}

.progress-bar:hover .progress-handle {
  opacity: 1;
}

.main-content {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: #94a3b8;
}

.empty-icon {
  font-size: 80px;
  margin-bottom: 20px;
}

.empty-state h2 {
  font-size: 24px;
  color: #e2e8f0;
  margin-bottom: 10px;
}

.empty-state p {
  font-size: 16px;
  margin-bottom: 30px;
}

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid #334155;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-overlay p {
  margin-top: 20px;
  font-size: 16px;
  color: #e2e8f0;
}
</style>
