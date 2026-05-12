<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useAgentStore } from '../stores/agent'
import spritesheetUrl from '../assets/pixel_pet_spritesheet.png'

const store = useAgentStore()
const petStatus = computed(() => store.petStatus)

const FRAME_W = 76
const FRAME_H = 56
const COLS = 4
const ROWS = 5
const SCALE = 4

const SPRITE_W = FRAME_W * SCALE
const SPRITE_H = FRAME_H * SCALE

const ROW_MAP = {
  IDLE: 2,
  THINKING: 3,
  SEARCHING: 0,
  REVIEWING: 0,
  WRITING: 4,
  ERROR: 4,
  DONE: 0,
}

const currentFrame = ref(0)
let frameTimer = null
let doneTimer = null

function getFrameSpeed(status) {
  switch (status) {
    case 'WRITING': return 100
    case 'ERROR': return 150
    case 'THINKING': return 350
    case 'SEARCHING': return 250
    case 'REVIEWING': return 300
    case 'DONE': return 200
    default: return 400
  }
}

function getFrameCount(status) {
  if (status === 'ERROR') return 4
  return COLS
}

function getStartFrame(status) {
  if (status === 'ERROR') return 0
  return 0
}

function startAnimation(status) {
  stopAnimation()
  if (doneTimer) {
    clearTimeout(doneTimer)
    doneTimer = null
  }

  const startFrame = getStartFrame(status)
  const frameCount = getFrameCount(status)
  const speed = getFrameSpeed(status)

  if (frameCount <= 1) {
    currentFrame.value = startFrame
    return
  }

  currentFrame.value = startFrame
  frameTimer = setInterval(() => {
    currentFrame.value = (currentFrame.value - startFrame + 1) % frameCount + startFrame
  }, speed)

  if (status === 'DONE') {
    doneTimer = setTimeout(() => {
      stopAnimation()
      startAnimation('IDLE')
    }, 4000)
  }
}

function stopAnimation() {
  if (frameTimer) {
    clearInterval(frameTimer)
    frameTimer = null
  }
  if (doneTimer) {
    clearTimeout(doneTimer)
    doneTimer = null
  }
}

watch(petStatus, (newStatus) => {
  startAnimation(newStatus)
}, { immediate: true })

onBeforeUnmount(() => {
  stopAnimation()
})

const spriteRow = computed(() => ROW_MAP[petStatus.value] ?? 2)

const bgPosition = computed(() => {
  const col = currentFrame.value
  const x = col * FRAME_W
  const y = spriteRow.value * FRAME_H
  return `-${x * SCALE}px -${y * SCALE}px`
})

const statusLabel = computed(() => {
  const map = {
    IDLE: '待命中',
    THINKING: '思考中...',
    SEARCHING: '搜索中...',
    REVIEWING: '审查中...',
    WRITING: '编码中...',
    ERROR: '出错了!',
    DONE: '完成!',
  }
  return map[petStatus.value] || '待命中'
})

const statusEmoji = computed(() => {
  const map = {
    IDLE: '🐱',
    THINKING: '🤔',
    SEARCHING: '🔍',
    REVIEWING: '🕵️',
    WRITING: '⌨️',
    ERROR: '💥',
    DONE: '✅',
  }
  return map[petStatus.value] || '🐱'
})

const statusColor = computed(() => {
  const map = {
    IDLE: '#4ade80',
    THINKING: '#60a5fa',
    SEARCHING: '#22d3ee',
    REVIEWING: '#c084fc',
    WRITING: '#f59e0b',
    ERROR: '#ef4444',
    DONE: '#a78bfa',
  }
  return map[petStatus.value] || '#4ade80'
})

const isError = computed(() => petStatus.value === 'ERROR')
</script>

<template>
  <div class="pixel-pet-container">
    <div class="pet-stage" :class="petStatus.toLowerCase()">
      <div
        class="sprite-canvas"
        :class="{ 'error-filter': isError }"
        :style="{
          width: SPRITE_W + 'px',
          height: SPRITE_H + 'px',
          backgroundImage: `url(${spritesheetUrl})`,
          backgroundSize: `${SPRITE_W * COLS}px ${SPRITE_H * ROWS}px`,
          backgroundPosition: bgPosition,
        }"
      ></div>

      <div class="effect-layer" v-if="petStatus === 'WRITING'">
        <span class="fire-particle fp1">🔥</span>
        <span class="fire-particle fp2">🔥</span>
        <span class="fire-particle fp3">💨</span>
      </div>

      <div class="effect-layer" v-if="petStatus === 'THINKING'">
        <span class="thought-bubble">💭</span>
      </div>

      <div class="effect-layer" v-if="petStatus === 'SEARCHING'">
        <span class="search-magnifier">🔍</span>
      </div>

      <div class="effect-layer" v-if="petStatus === 'REVIEWING'">
        <span class="review-magnifier">🕵️</span>
        <span class="review-shield">🛡️</span>
      </div>

      <div class="effect-layer" v-if="petStatus === 'ERROR'">
        <span class="panic-mark">❗</span>
        <span class="sweat-drop">💧</span>
      </div>

      <div class="effect-layer" v-if="petStatus === 'DONE'">
        <span class="sparkle sp1">✨</span>
        <span class="sparkle sp2">⭐</span>
        <span class="sparkle sp3">✨</span>
      </div>
    </div>

    <div class="status-badge" :style="{ borderColor: statusColor, color: statusColor }">
      {{ statusEmoji }} {{ statusLabel }}
    </div>
  </div>
</template>

<style scoped>
.pixel-pet-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 90;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.pet-stage {
  position: relative;
  image-rendering: pixelated;
}

.sprite-canvas {
  image-rendering: pixelated;
  image-rendering: -moz-crisp-edges;
  image-rendering: crisp-edges;
  background-repeat: no-repeat;
  transition: background-position 0.08s steps(1);
}

.error-filter {
  filter: brightness(0.7) saturate(2) hue-rotate(-30deg) drop-shadow(0 0 6px rgba(239, 68, 68, 0.8));
}

.idle .sprite-canvas {
  animation: idle-bob 2s ease-in-out infinite;
}

.thinking .sprite-canvas {
  animation: thinking-sway 1.2s ease-in-out infinite;
}

.searching .sprite-canvas {
  animation: searching-pace 0.6s ease-in-out infinite;
}

.reviewing .sprite-canvas {
  animation: reviewing-scan 1s ease-in-out infinite;
}

.writing .sprite-canvas {
  animation: writing-bounce 0.25s ease-in-out infinite;
}

.error .sprite-canvas {
  animation: error-shake 0.12s ease-in-out infinite, error-flash 0.4s ease-in-out infinite;
}

@keyframes error-flash {
  0%, 100% { filter: brightness(0.7) saturate(2) hue-rotate(-30deg) drop-shadow(0 0 6px rgba(239, 68, 68, 0.8)); }
  50% { filter: brightness(1.2) saturate(2.5) hue-rotate(-30deg) drop-shadow(0 0 12px rgba(239, 68, 68, 1)); }
}

.done .sprite-canvas {
  animation: done-jump 0.5s ease-in-out 3;
}

@keyframes idle-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

@keyframes thinking-sway {
  0%, 100% { transform: translateX(0) rotate(0deg); }
  25% { transform: translateX(-3px) rotate(-2deg); }
  75% { transform: translateX(3px) rotate(2deg); }
}

@keyframes searching-pace {
  0%, 100% { transform: translateX(0); }
  30% { transform: translateX(4px); }
  60% { transform: translateX(-4px); }
}

@keyframes writing-bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

@keyframes error-shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-5px); }
  75% { transform: translateX(5px); }
}

@keyframes done-jump {
  0%, 100% { transform: translateY(0); }
  40% { transform: translateY(-14px); }
}

.effect-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.fire-particle {
  position: absolute;
  font-size: 14px;
  animation: fire-rise 0.6s ease-out infinite;
}

.fp1 { top: -8px; left: 25%; animation-delay: 0s; }
.fp2 { top: -8px; left: 55%; animation-delay: 0.2s; }
.fp3 { top: -12px; left: 75%; animation-delay: 0.4s; font-size: 10px; }

@keyframes fire-rise {
  0% { opacity: 1; transform: translateY(0) scale(1); }
  100% { opacity: 0; transform: translateY(-20px) scale(0.4); }
}

.thought-bubble {
  position: absolute;
  top: -18px;
  right: -12px;
  font-size: 18px;
  animation: thought-pulse 1.2s ease-in-out infinite;
}

.search-magnifier {
  position: absolute;
  top: -16px;
  right: -10px;
  font-size: 16px;
  animation: search-scan 1s ease-in-out infinite;
}

@keyframes search-scan {
  0%, 100% { transform: translate(0, 0) scale(1); }
  30% { transform: translate(6px, -4px) scale(1.1); }
  60% { transform: translate(-4px, 2px) scale(0.9); }
}

@keyframes reviewing-scan {
  0%, 100% { transform: translateX(0) rotate(0deg); }
  25% { transform: translateX(3px) rotate(1deg); }
  50% { transform: translateX(-3px) rotate(-1deg); }
  75% { transform: translateX(2px) rotate(0.5deg); }
}

.review-magnifier {
  position: absolute;
  top: -16px;
  right: -10px;
  font-size: 16px;
  animation: review-inspect 1.2s ease-in-out infinite;
}

.review-shield {
  position: absolute;
  bottom: -4px;
  left: -12px;
  font-size: 12px;
  animation: review-pulse 1.5s ease-in-out infinite;
}

@keyframes review-inspect {
  0%, 100% { transform: translate(0, 0) scale(1); }
  40% { transform: translate(-8px, 4px) scale(1.2); }
  70% { transform: translate(4px, -2px) scale(0.9); }
}

@keyframes review-pulse {
  0%, 100% { opacity: 0.6; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.1); }
}

@keyframes thought-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.2); }
}

.panic-mark {
  position: absolute;
  top: -14px;
  right: -8px;
  font-size: 16px;
  animation: panic-flash 0.3s ease-in-out infinite;
}

.sweat-drop {
  position: absolute;
  top: -4px;
  left: -10px;
  font-size: 12px;
  animation: sweat-fall 0.8s ease-in infinite;
}

@keyframes panic-flash {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.3); }
}

@keyframes sweat-fall {
  0% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(14px); }
}

.sparkle {
  position: absolute;
  font-size: 14px;
  animation: sparkle-float 1s ease-in-out infinite;
}

.sp1 { top: -10px; left: -6px; animation-delay: 0s; }
.sp2 { top: -14px; left: 50%; animation-delay: 0.3s; }
.sp3 { top: -10px; right: -6px; animation-delay: 0.6s; }

@keyframes sparkle-float {
  0%, 100% { opacity: 0.3; transform: scale(0.7); }
  50% { opacity: 1; transform: scale(1.2); }
}

.status-badge {
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  padding: 3px 10px;
  border: 1px solid;
  border-radius: 3px;
  background: rgba(10, 10, 10, 0.92);
  letter-spacing: 0.5px;
  white-space: nowrap;
  backdrop-filter: blur(4px);
}
</style>
