<template>
  <div class="piano-roll-container">
    <!-- Canvas 画布 -->
    <canvas 
      ref="canvasRef"
      @mousedown="handleMouseDown"
      @mousemove="handleMouseMove"
      @mouseup="handleMouseUp"
      @wheel="handleWheel"
    ></canvas>
    
    <!-- 垂直滚动条 -->
    <div class="vertical-scrollbar">
      <div 
        class="scrollbar-thumb"
        :style="scrollbarThumbStyle"
        @mousedown="handleScrollbarMouseDown"
      ></div>
    </div>
    
    <!-- 信息提示 -->
    <div class="info-panel" v-if="selectedNotes.length > 0">
      <p>已选择 {{ selectedNotes.length }} 个音符</p>
      <button @click="setSelectedAsMelody" class="btn-melody">设为旋律</button>
      <button @click="setSelectedAsAccompaniment" class="btn-accomp">设为伴奏</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  notes: {
    type: Array,
    default: () => []
  },
  duration: {
    type: Number,
    default: 0
  },
  currentTime: {
    type: Number,
    default: 0
  },
  isPlaying: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:notes', 'play-note'])

// Canvas 引用
const canvasRef = ref(null)
let ctx = null

// 视图参数
const VIEW = {
  pixelsPerSecond: 100, // 每秒对应的像素数
  pixelsPerPitch: 12,   // 每个音高对应的像素数（从8增加到12）
  minPitch: 21,         // 最低音 A0
  maxPitch: 108,        // 最高音 C8
  offsetX: 0,           // 水平偏移
  offsetY: 0,           // 垂直偏移
  width: 0,
  height: 0
}

// 交互状态
const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const dragEnd = ref({ x: 0, y: 0 })
const selectedNotes = ref([])

// 滚动条状态
const isScrollbarDragging = ref(false)
const scrollbarDragStart = ref(0)

// 颜色配置
const COLORS = {
  melody: '#4ade80',      // 亮绿色
  accompaniment: '#4b5563', // 暗灰色
  selected: '#fbbf24',     // 选中高亮黄色
  background: '#0f172a',   // 深色背景
  grid: '#1e293b',         // 网格线
  whiteKey: '#f1f5f9',     // 白键
  blackKey: '#334155'      // 黑键
}

// 黑键音高集合 (C#, D#, F#, G#, A#)
const BLACK_KEYS = new Set([1, 3, 6, 8, 10])

// 计算滚动条样式
const scrollbarThumbStyle = ref({})

const updateScrollbarThumbStyle = () => {
  if (!VIEW.height) return
  
  // 总内容高度（所有音符的范围）
  const totalContentHeight = (VIEW.maxPitch - VIEW.minPitch) * VIEW.pixelsPerPitch
  
  // 可视区域占总内容的比例
  const visibleRatio = VIEW.height / totalContentHeight
  
  // 滚动条滑块高度（至少30px）
  const thumbHeight = Math.max(30, VIEW.height * visibleRatio)
  
  // 当前滚动位置的比例
  const maxOffsetY = totalContentHeight - VIEW.height
  const scrollRatio = maxOffsetY > 0 ? VIEW.offsetY / maxOffsetY : 0
  
  // 滚动条滑块的top位置
  const maxThumbTop = VIEW.height - thumbHeight
  const thumbTop = maxThumbTop * scrollRatio
  
  scrollbarThumbStyle.value = {
    height: `${thumbHeight}px`,
    top: `${thumbTop}px`
  }
}

/**
 * 初始化 Canvas
 */
const initCanvas = () => {
  const canvas = canvasRef.value
  if (!canvas) return
  
  ctx = canvas.getContext('2d')
  
  // 设置 Canvas 尺寸为容器尺寸
  const rect = canvas.parentElement.getBoundingClientRect()
  VIEW.width = canvas.width = rect.width
  VIEW.height = canvas.height = rect.height
  
  // 初始偏移：垂直方向居中在 C4 (MIDI 60) 附近
  VIEW.offsetY = (60 - VIEW.minPitch) * VIEW.pixelsPerPitch - VIEW.height / 2
  
  updateScrollbarThumbStyle()
  render()
}

/**
 * 渲染主函数
 */
const render = () => {
  if (!ctx) return
  
  // 清空画布
  ctx.fillStyle = COLORS.background
  ctx.fillRect(0, 0, VIEW.width, VIEW.height)
  
  // 绘制网格和钢琴键
  drawGrid()
  drawPianoKeys()
  
  // 绘制音符
  drawNotes()
  
  // 绘制播放进度条
  if (props.currentTime > 0) {
    drawProgressLine()
  }
  
  // 绘制框选区域
  if (isDragging.value) {
    drawSelectionBox()
  }
}

/**
 * 绘制网格
 */
const drawGrid = () => {
  ctx.strokeStyle = COLORS.grid
  ctx.lineWidth = 1
  
  // 垂直网格线 (每秒一条)
  const startTime = Math.floor(VIEW.offsetX / VIEW.pixelsPerSecond)
  const endTime = Math.ceil((VIEW.offsetX + VIEW.width) / VIEW.pixelsPerSecond)
  
  for (let t = startTime; t <= endTime; t++) {
    const x = t * VIEW.pixelsPerSecond - VIEW.offsetX
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, VIEW.height)
    ctx.stroke()
  }
  
  // 水平网格线 (每个音高一条)
  for (let pitch = VIEW.minPitch; pitch <= VIEW.maxPitch; pitch++) {
    const y = pitchToY(pitch)
    if (y < 0 || y > VIEW.height) continue
    
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(VIEW.width, y)
    ctx.stroke()
  }
}

/**
 * 绘制钢琴键位指示
 */
const drawPianoKeys = () => {
  const keyWidth = 60
  
  for (let pitch = VIEW.minPitch; pitch <= VIEW.maxPitch; pitch++) {
    const y = pitchToY(pitch)
    if (y < 0 || y > VIEW.height) continue
    
    const noteInOctave = pitch % 12
    const isBlackKey = BLACK_KEYS.has(noteInOctave)
    
    ctx.fillStyle = isBlackKey ? COLORS.blackKey : COLORS.whiteKey
    ctx.fillRect(0, y, keyWidth, VIEW.pixelsPerPitch)
    
    // 绘制音名 (只在 C 音显示)
    if (noteInOctave === 0) {
      ctx.fillStyle = '#94a3b8'
      ctx.font = '10px monospace'
      ctx.fillText(`C${Math.floor(pitch / 12) - 1}`, 5, y + VIEW.pixelsPerPitch - 2)
    }
  }
}

/**
 * 绘制所有音符
 */
const drawNotes = () => {
  props.notes.forEach(note => {
    drawNote(note, selectedNotes.value.includes(note.id))
  })
}

/**
 * 绘制单个音符
 */
const drawNote = (note, isSelected) => {
  const x = timeToX(note.start)
  const y = pitchToY(note.pitch)
  const width = (note.end - note.start) * VIEW.pixelsPerSecond
  const height = VIEW.pixelsPerPitch
  
  // 裁剪检查
  if (x + width < 0 || x > VIEW.width || y + height < 0 || y > VIEW.height) {
    return
  }
  
  // 选择颜色
  let color = note.is_melody ? COLORS.melody : COLORS.accompaniment
  if (isSelected) {
    color = COLORS.selected
  }
  
  ctx.fillStyle = color
  ctx.fillRect(x, y, width, height)
  
  // 绘制边框
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.3)'
  ctx.lineWidth = 1
  ctx.strokeRect(x, y, width, height)
}

/**
 * 绘制播放进度条
 */
const drawProgressLine = () => {
  const x = timeToX(props.currentTime)
  
  // 只在可见区域内绘制
  if (x < 0 || x > VIEW.width) return
  
  // 绘制已播放区域的半透明遮罩
  ctx.fillStyle = 'rgba(239, 68, 68, 0.08)'
  ctx.fillRect(0, 0, x, VIEW.height)
  
  // 绘制进度线（带阴影效果）
  ctx.save()
  ctx.shadowColor = 'rgba(239, 68, 68, 0.5)'
  ctx.shadowBlur = 6
  ctx.strokeStyle = '#ef4444'  // 红色
  ctx.lineWidth = 2  // 从 3 改为 2，更细
  ctx.setLineDash([])
  ctx.beginPath()
  ctx.moveTo(x, 0)
  ctx.lineTo(x, VIEW.height)
  ctx.stroke()
  ctx.restore()
  
  // 绘制顶部三角形标记
  ctx.fillStyle = '#ef4444'
  ctx.beginPath()
  ctx.moveTo(x, 0)
  ctx.lineTo(x - 8, 15)
  ctx.lineTo(x + 8, 15)
  ctx.closePath()
  ctx.fill()
  
  // 绘制底部三角形标记
  ctx.beginPath()
  ctx.moveTo(x, VIEW.height)
  ctx.lineTo(x - 8, VIEW.height - 15)
  ctx.lineTo(x + 8, VIEW.height - 15)
  ctx.closePath()
  ctx.fill()
  
  // 绘制时间标签
  const mins = Math.floor(props.currentTime / 60)
  const secs = Math.floor(props.currentTime % 60)
  const timeText = `${mins}:${secs.toString().padStart(2, '0')}`
  
  ctx.font = 'bold 12px monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  
  // 时间标签背景
  const textWidth = ctx.measureText(timeText).width
  const labelX = Math.min(Math.max(x, textWidth / 2 + 5), VIEW.width - textWidth / 2 - 5)
  const labelY = 20
  
  ctx.fillStyle = 'rgba(239, 68, 68, 0.9)'
  ctx.fillRect(labelX - textWidth / 2 - 4, labelY, textWidth + 8, 18)
  
  // 时间文字
  ctx.fillStyle = '#ffffff'
  ctx.fillText(timeText, labelX, labelY + 3)
}

/**
 * 绘制框选区域
 */
const drawSelectionBox = () => {
  const x = Math.min(dragStart.value.x, dragEnd.value.x)
  const y = Math.min(dragStart.value.y, dragEnd.value.y)
  const width = Math.abs(dragEnd.value.x - dragStart.value.x)
  const height = Math.abs(dragEnd.value.y - dragStart.value.y)
  
  ctx.strokeStyle = COLORS.selected
  ctx.lineWidth = 2
  ctx.setLineDash([5, 5])
  ctx.strokeRect(x, y, width, height)
  ctx.setLineDash([])
  
  ctx.fillStyle = 'rgba(251, 191, 36, 0.1)'
  ctx.fillRect(x, y, width, height)
}

/**
 * 坐标转换：时间 -> X 像素
 */
const timeToX = (time) => {
  return time * VIEW.pixelsPerSecond - VIEW.offsetX
}

/**
 * 坐标转换：音高 -> Y 像素
 */
const pitchToY = (pitch) => {
  return (VIEW.maxPitch - pitch) * VIEW.pixelsPerPitch - VIEW.offsetY
}

/**
 * 坐标转换：X 像素 -> 时间
 */
const xToTime = (x) => {
  return (x + VIEW.offsetX) / VIEW.pixelsPerSecond
}

/**
 * 坐标转换：Y 像素 -> 音高
 */
const yToPitch = (y) => {
  return VIEW.maxPitch - Math.floor((y + VIEW.offsetY) / VIEW.pixelsPerPitch)
}

/**
 * 获取鼠标点击的音符
 */
const getNoteAtPosition = (x, y) => {
  const time = xToTime(x)
  const pitch = yToPitch(y)
  
  return props.notes.find(note => 
    note.pitch === pitch &&
    note.start <= time &&
    note.end >= time
  )
}

/**
 * 获取框选区域内的音符
 */
const getNotesInBox = (x1, y1, x2, y2) => {
  const minX = Math.min(x1, x2)
  const maxX = Math.max(x1, x2)
  const minY = Math.min(y1, y2)
  const maxY = Math.max(y1, y2)
  
  const startTime = xToTime(minX)
  const endTime = xToTime(maxX)
  const maxPitch = yToPitch(minY)
  const minPitch = yToPitch(maxY)
  
  return props.notes.filter(note => {
    const noteStartX = timeToX(note.start)
    const noteEndX = timeToX(note.end)
    const noteY = pitchToY(note.pitch)
    
    return noteEndX >= minX && noteStartX <= maxX &&
           noteY >= minY && noteY <= maxY
  })
}

/**
 * 鼠标按下事件
 */
const handleMouseDown = (e) => {
  const rect = canvasRef.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  
  // 检查是否点击到音符
  const clickedNote = getNoteAtPosition(x, y)
  
  if (clickedNote && !e.shiftKey) {
    // 单击音符：切换旋律状态并播放该音符
    toggleNoteMelody(clickedNote.id)
    // 触发播放音符事件
    emit('play-note', clickedNote.pitch, clickedNote.velocity, 0.3)
  } else {
    // 开始框选
    isDragging.value = true
    dragStart.value = { x, y }
    dragEnd.value = { x, y }
  }
}

/**
 * 鼠标移动事件
 */
const handleMouseMove = (e) => {
  if (!isDragging.value) return
  
  const rect = canvasRef.value.getBoundingClientRect()
  dragEnd.value = {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  }
  
  // 更新选中的音符
  const notesInBox = getNotesInBox(
    dragStart.value.x,
    dragStart.value.y,
    dragEnd.value.x,
    dragEnd.value.y
  )
  selectedNotes.value = notesInBox.map(n => n.id)
  
  render()
}

/**
 * 鼠标释放事件
 */
const handleMouseUp = () => {
  if (isDragging.value) {
    isDragging.value = false
    render()
  }
}

/**
 * 鼠标滚轮事件（缩放和平移）
 */
const handleWheel = (e) => {
  e.preventDefault()
  
  if (e.ctrlKey) {
    // Ctrl + 滚轮：水平缩放
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1
    VIEW.pixelsPerSecond *= zoomFactor
    VIEW.pixelsPerSecond = Math.max(20, Math.min(500, VIEW.pixelsPerSecond))
  } else if (e.shiftKey) {
    // Shift + 滚轮：垂直平移
    VIEW.offsetY += e.deltaY
    const maxOffsetY = (VIEW.maxPitch - VIEW.minPitch) * VIEW.pixelsPerPitch - VIEW.height
    VIEW.offsetY = Math.max(0, Math.min(maxOffsetY, VIEW.offsetY))
    updateScrollbarThumbStyle()
  } else {
    // 普通滚轮：水平平移（左右滑动）
    VIEW.offsetX += e.deltaY
    VIEW.offsetX = Math.max(0, VIEW.offsetX)
  }
  
  render()
}

/**
 * 滚动条鼠标按下事件
 */
const handleScrollbarMouseDown = (e) => {
  e.preventDefault()
  isScrollbarDragging.value = true
  scrollbarDragStart.value = e.clientY
  
  // 添加全局鼠标事件监听
  document.addEventListener('mousemove', handleScrollbarMouseMove)
  document.addEventListener('mouseup', handleScrollbarMouseUp)
}

/**
 * 滚动条拖动事件
 */
const handleScrollbarMouseMove = (e) => {
  if (!isScrollbarDragging.value) return
  
  const deltaY = e.clientY - scrollbarDragStart.value
  scrollbarDragStart.value = e.clientY
  
  // 计算滚动距离
  const totalContentHeight = (VIEW.maxPitch - VIEW.minPitch) * VIEW.pixelsPerPitch
  const maxOffsetY = totalContentHeight - VIEW.height
  
  // 滚动条移动比例转换为内容偏移
  const scrollRatio = deltaY / VIEW.height
  VIEW.offsetY += scrollRatio * totalContentHeight
  VIEW.offsetY = Math.max(0, Math.min(maxOffsetY, VIEW.offsetY))
  
  updateScrollbarThumbStyle()
  render()
}

/**
 * 滚动条鼠标释放事件
 */
const handleScrollbarMouseUp = () => {
  isScrollbarDragging.value = false
  document.removeEventListener('mousemove', handleScrollbarMouseMove)
  document.removeEventListener('mouseup', handleScrollbarMouseUp)
}

/**
 * 切换音符的旋律状态
 */
const toggleNoteMelody = (noteId) => {
  const updatedNotes = props.notes.map(note => {
    if (note.id === noteId) {
      return { ...note, is_melody: !note.is_melody }
    }
    return note
  })
  emit('update:notes', updatedNotes)
}

/**
 * 将选中的音符设为旋律
 */
const setSelectedAsMelody = () => {
  const updatedNotes = props.notes.map(note => {
    if (selectedNotes.value.includes(note.id)) {
      return { ...note, is_melody: true }
    }
    return note
  })
  emit('update:notes', updatedNotes)
  selectedNotes.value = []
}

/**
 * 将选中的音符设为伴奏
 */
const setSelectedAsAccompaniment = () => {
  const updatedNotes = props.notes.map(note => {
    if (selectedNotes.value.includes(note.id)) {
      return { ...note, is_melody: false }
    }
    return note
  })
  emit('update:notes', updatedNotes)
  selectedNotes.value = []
}

// 监听 notes 变化，重新渲染
watch(() => props.notes, () => {
  render()
}, { deep: true })

// 监听播放进度，自动滚动
watch(() => props.currentTime, (newTime, oldTime) => {
  if (props.isPlaying && newTime > 0) {
    autoScroll(newTime)
  }
  // 当播放停止并重置到开头时，滚动回起始位置
  if (newTime === 0 && oldTime > 0 && !props.isPlaying) {
    VIEW.offsetX = 0
  }
  render()
})

/**
 * 自动滚动以跟随播放进度
 */
const autoScroll = (currentTime) => {
  const progressX = timeToX(currentTime)
  const viewportCenter = VIEW.width / 2
  
  // 当进度条超过视口中心位置时，开始滚动
  if (progressX > viewportCenter) {
    // 让进度条保持在视口中心偏左的位置
    const targetOffsetX = currentTime * VIEW.pixelsPerSecond - viewportCenter + 100
    VIEW.offsetX = Math.max(0, targetOffsetX)
  }
}

/**
 * 滚动到指定时间位置（供父组件调用）
 */
const scrollToTime = (time) => {
  const targetX = time * VIEW.pixelsPerSecond
  const viewportCenter = VIEW.width / 2
  
  // 让目标时间显示在视口中心偏左位置
  VIEW.offsetX = Math.max(0, targetX - viewportCenter + 100)
  render()
}

// 暴露方法给父组件
defineExpose({
  scrollToTime
})

// 生命周期
onMounted(() => {
  initCanvas()
  window.addEventListener('resize', initCanvas)
})

onUnmounted(() => {
  window.removeEventListener('resize', initCanvas)
})
</script>

<style scoped>
.piano-roll-container {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

canvas {
  display: block;
  cursor: crosshair;
}

/* 垂直滚动条 */
.vertical-scrollbar {
  position: absolute;
  top: 0;
  right: 0;
  width: 12px;
  height: 100%;
  background: rgba(15, 23, 42, 0.8);
  border-left: 1px solid #334155;
}

.scrollbar-thumb {
  position: absolute;
  width: 100%;
  background: #64748b;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.scrollbar-thumb:hover {
  background: #94a3b8;
}

.scrollbar-thumb:active {
  background: #cbd5e1;
}

.info-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 15px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
}

.info-panel p {
  margin-bottom: 10px;
  color: #e2e8f0;
  font-size: 14px;
}

.info-panel button {
  margin-right: 8px;
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-melody {
  background: #4ade80;
  color: #0f172a;
}

.btn-melody:hover {
  background: #22c55e;
}

.btn-accomp {
  background: #4b5563;
  color: #f1f5f9;
}

.btn-accomp:hover {
  background: #6b7280;
}
</style>
