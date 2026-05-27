<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  visible: Boolean
})
const emit = defineEmits(['close'])

const canvasRef = ref(null)
const nodes = ref([])
const edges = ref([])
const animFrame = ref(null)
const hoveredNode = ref(null)

const mockNodes = [
  { id: 'tcp', label: 'TCP/IP', x: 340, y: 180, r: 28, color: '#00ff88', group: 'network' },
  { id: 'http', label: 'HTTP', x: 440, y: 120, r: 24, color: '#00cc6a', group: 'network' },
  { id: 'epoll', label: 'epoll', x: 240, y: 130, r: 22, color: '#7c3aed', group: 'system' },
  { id: 'muduo', label: 'Muduo', x: 300, y: 260, r: 26, color: '#7c3aed', group: 'framework' },
  { id: 'thread', label: '多线程', x: 180, y: 240, r: 22, color: '#f59e0b', group: 'concurrent' },
  { id: 'mutex', label: 'Mutex', x: 120, y: 170, r: 18, color: '#f59e0b', group: 'concurrent' },
  { id: 'rbtree', label: '红黑树', x: 400, y: 280, r: 22, color: '#ef4444', group: 'datastructure' },
  { id: 'avl', label: 'AVL', x: 480, y: 220, r: 18, color: '#ef4444', group: 'datastructure' },
  { id: 'dp', label: '动态规划', x: 520, y: 300, r: 20, color: '#06b6d4', group: 'algorithm' },
  { id: 'dfs', label: 'DFS/BFS', x: 460, y: 350, r: 18, color: '#06b6d4', group: 'algorithm' },
]

const mockEdges = [
  ['tcp', 'http'], ['tcp', 'epoll'], ['tcp', 'muduo'],
  ['muduo', 'epoll'], ['muduo', 'thread'], ['thread', 'mutex'],
  ['rbtree', 'avl'], ['dp', 'dfs'],
  ['http', 'muduo'], ['rbtree', 'muduo'],
]

function initCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)
  nodes.value = mockNodes
  edges.value = mockEdges
  draw(ctx, rect.width, rect.height)
}

function draw(ctx, w, h) {
  ctx.clearRect(0, 0, w, h)

  const t = Date.now() / 1000

  edges.value.forEach(([fromId, toId]) => {
    const from = nodes.value.find(n => n.id === fromId)
    const to = nodes.value.find(n => n.id === toId)
    if (!from || !to) return
    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)
    ctx.strokeStyle = 'rgba(0, 255, 136, 0.12)'
    ctx.lineWidth = 1
    ctx.stroke()

    const progress = ((t * 0.3) % 1)
    const px = from.x + (to.x - from.x) * progress
    const py = from.y + (to.y - from.y) * progress
    ctx.beginPath()
    ctx.arc(px, py, 2, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(0, 255, 136, 0.4)'
    ctx.fill()
  })

  nodes.value.forEach(node => {
    const pulse = Math.sin(t * 2 + node.x * 0.01) * 2
    const isHovered = hoveredNode.value === node.id
    const r = node.r + (isHovered ? 4 : 0) + pulse * 0.3

    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 8, 0, Math.PI * 2)
    ctx.fillStyle = node.color + '08'
    ctx.fill()

    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 3, 0, Math.PI * 2)
    ctx.fillStyle = node.color + '15'
    ctx.fill()

    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
    const grad = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, r)
    grad.addColorStop(0, node.color + '40')
    grad.addColorStop(1, node.color + '15')
    ctx.fillStyle = grad
    ctx.fill()

    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
    ctx.strokeStyle = node.color + (isHovered ? 'cc' : '60')
    ctx.lineWidth = isHovered ? 2 : 1
    ctx.stroke()

    ctx.fillStyle = isHovered ? '#ffffff' : '#d4d4d4'
    ctx.font = `${isHovered ? 'bold ' : ''}${r < 20 ? 9 : 10}px "JetBrains Mono", monospace`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(node.label, node.x, node.y)
  })

  animFrame.value = requestAnimationFrame(() => draw(ctx, w, h))
}

function handleMouseMove(e) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  hoveredNode.value = null
  for (const node of nodes.value) {
    const dx = mx - node.x
    const dy = my - node.y
    if (dx * dx + dy * dy < node.r * node.r) {
      hoveredNode.value = node.id
      canvas.style.cursor = 'pointer'
      return
    }
  }
  canvas.style.cursor = 'default'
}

onMounted(() => {
  if (props.visible) {
    setTimeout(initCanvas, 100)
  }
})

onBeforeUnmount(() => {
  if (animFrame.value) cancelAnimationFrame(animFrame.value)
})
</script>

<template>
  <Transition name="panel-slide">
    <div v-if="visible" class="fixed inset-0 z-[100] flex justify-end" @click.self="emit('close')">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
      <div class="relative w-[680px] max-w-[90vw] h-full bg-geek-surface border-l border-cyan-500/20 shadow-[0_0_30px_rgba(0,255,136,0.08)] flex flex-col">
        <div class="flex items-center justify-between px-5 py-4 border-b border-geek-border shrink-0">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-cyan-900/30 border border-cyan-500/30 flex items-center justify-center text-sm">🌳</div>
            <div>
              <div class="text-sm font-bold text-cyan-400">知识图谱</div>
              <div class="text-[10px] text-geek-text-dim">技能关联网络 & 知识脉络</div>
            </div>
          </div>
          <button @click="emit('close')" class="text-geek-text-dim hover:text-geek-text text-lg leading-none">×</button>
        </div>

        <div class="flex-1 relative overflow-hidden">
          <canvas ref="canvasRef" class="w-full h-full" @mousemove="handleMouseMove"></canvas>

          <div class="absolute top-3 left-4 space-y-1">
            <div class="flex items-center gap-2 text-[10px]">
              <span class="w-2 h-2 rounded-full bg-[#00ff88]"></span>
              <span class="text-geek-text-dim">网络</span>
              <span class="w-2 h-2 rounded-full bg-[#7c3aed]"></span>
              <span class="text-geek-text-dim">系统/框架</span>
              <span class="w-2 h-2 rounded-full bg-[#f59e0b]"></span>
              <span class="text-geek-text-dim">并发</span>
              <span class="w-2 h-2 rounded-full bg-[#ef4444]"></span>
              <span class="text-geek-text-dim">数据结构</span>
              <span class="w-2 h-2 rounded-full bg-[#06b6d4]"></span>
              <span class="text-geek-text-dim">算法</span>
            </div>
          </div>

          <div v-if="hoveredNode" class="absolute bottom-4 left-4 bg-geek-bg/90 backdrop-blur-sm border border-geek-border rounded-lg px-3 py-2">
            <div class="text-xs font-bold text-geek-accent">{{ nodes.find(n => n.id === hoveredNode)?.label }}</div>
            <div class="text-[10px] text-geek-text-dim mt-0.5">
              关联: {{ edges.filter(([a, b]) => a === hoveredNode || b === hoveredNode).length }} 条连线
            </div>
          </div>
        </div>

        <div class="px-5 py-3 border-t border-geek-border shrink-0">
          <div class="text-[10px] text-geek-text-dim">⚡ 知识图谱由 Neo4j 驱动，节点随编程实践自动生长。当前为预览模式。</div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.panel-slide-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.panel-slide-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}
.panel-slide-enter-from {
  opacity: 0;
}
.panel-slide-enter-from > :nth-child(2) {
  transform: translateX(100%);
}
.panel-slide-leave-to {
  opacity: 0;
}
.panel-slide-leave-to > :nth-child(2) {
  transform: translateX(100%);
}
.panel-slide-enter-active > :nth-child(2) {
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.panel-slide-leave-active > :nth-child(2) {
  transition: transform 0.25s cubic-bezier(0.4, 0, 1, 1);
}
</style>
