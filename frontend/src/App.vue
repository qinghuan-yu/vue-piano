<template>
  <div class="app-container">
    <!-- 顶部控制栏 -->
    <header class="control-bar">
      <div class="logo">
        <h1>🎹 Animenz Melody Annotator</h1>
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
        
        <!-- Solo 模式 -->
        <label class="checkbox-label">
          <input 
            type="checkbox" 
            v-model="soloMode"
            :disabled="!midiData"
          />
          <span>Solo Melody</span>
        </label>
        
        <!-- 导出按钮 -->
        <button 
          class="btn btn-accent" 
          @click="exportMidi"
          :disabled="!midiData"
        >
          💾 导出分轨
        </button>
        
        <!-- 统计信息 -->
        <div class="stats" v-if="midiData">
          <span class="stat-item melody">旋律: {{ melodyCount }}</span>
          <span class="stat-item accomp">伴奏: {{ accompCount }}</span>
          <span class="stat-item total">总计: {{ totalNotes }}</span>
        </div>
      </div>
    </header>
    
    <!-- 主视图区域 -->
    <main class="main-content">
      <div v-if="!midiData" class="empty-state">
        <div class="empty-icon">🎼</div>
        <h2>欢迎使用 Animenz Melody Annotator</h2>
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
        v-else
        :notes="midiData.notes"
        :duration="midiData.duration"
        @update:notes="handleNotesUpdate"
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
import { ref, computed } from 'vue'
import axios from 'axios'
import * as Tone from 'tone'
import PianoRoll from './components/PianoRoll.vue'

// 状态管理
const midiData = ref(null)
const isLoading = ref(false)
const loadingText = ref('处理中...')
const isPlaying = ref(false)
const soloMode = ref(false)

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
  
  isLoading.value = true
  loadingText.value = '正在分析 MIDI 文件...'
  
  try {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await axios.post(`${API_BASE}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    midiData.value = response.data
    console.log('MIDI 数据加载成功:', response.data)
  } catch (error) {
    console.error('上传失败:', error)
    alert('上传失败：' + (error.response?.data?.detail || error.message))
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
  await Tone.start()
  initSynth()
  
  isPlaying.value = true
  const now = Tone.now()
  
  // 筛选要播放的音符
  const notesToPlay = soloMode.value 
    ? midiData.value.notes.filter(n => n.is_melody)
    : midiData.value.notes
  
  // 调度所有音符
  notesToPlay.forEach(note => {
    const midiNote = Tone.Frequency(note.pitch, 'midi').toNote()
    const duration = note.end - note.start
    const velocity = note.velocity / 127
    
    scheduledNotes.push(
      Tone.Transport.schedule((time) => {
        synth.triggerAttackRelease(midiNote, duration, time, velocity)
      }, now + note.start)
    )
  })
  
  // 播放完成后停止
  const duration = midiData.value.duration
  Tone.Transport.schedule(() => {
    stopPlayback()
  }, now + duration)
  
  Tone.Transport.start()
}

/**
 * 停止播放
 */
const stopPlayback = () => {
  isPlaying.value = false
  Tone.Transport.stop()
  Tone.Transport.cancel()
  scheduledNotes = []
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
    
    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'separated_midi.zip')
    document.body.appendChild(link)
    link.click()
    link.remove()
    
    console.log('导出成功')
  } catch (error) {
    console.error('导出失败:', error)
    alert('导出失败：' + (error.response?.data?.detail || error.message))
  } finally {
    isLoading.value = false
  }
}
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

.btn-large {
  padding: 12px 24px;
  font-size: 16px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #e2e8f0;
  font-size: 14px;
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  cursor: pointer;
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
