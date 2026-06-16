<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  visible: Boolean
})
const emit = defineEmits(['close'])

const chartRef = ref(null)
let chartInstance = null
let layoutTimer = null

// 分类颜色映射
const categoryColors = {
  'entity': '#00ff88',
  'concept': '#7c3aed',
  'default': '#06b6d4',
}

// 从后端获取图谱数据
async function fetchGraphData() {
  try {
    const token = localStorage.getItem('token')
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    // 尝试从 localStorage 获取 user_id
    let userId = ''
    try {
      const userInfo = JSON.parse(localStorage.getItem('userInfo') || '{}')
      userId = userInfo.user_id || ''
    } catch (e) { /* ignore */ }

    if (userId) {
      headers['X-User-Id'] = userId
    }

    const resp = await fetch('/api/v1/graph/data?max_nodes=80', { headers })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    return data
  } catch (e) {
    console.warn('[KnowledgeGraph] Failed to fetch graph data:', e)
    return null
  }
}

function buildEChartsOption(graphData) {
  const rawNodes = graphData.nodes || []
  const rawLinks = graphData.links || graphData.edges || []

  // 构建节点
  const nodes = rawNodes.map(n => ({
    id: n.id || n.name,
    name: n.id || n.name,
    symbolSize: Math.max(12, Math.min(40, 8 + (n.val || 10))),
    category: n.category || 'default',
    itemStyle: {
      color: categoryColors[n.category] || categoryColors['default'],
      borderColor: 'rgba(0,0,0,0.3)',
      borderWidth: 1,
    },
    label: {
      show: true,
      fontSize: 10,
      color: '#d4d4d4',
    },
  }))

  // 构建边
  const links = rawLinks.map(l => ({
    source: l.source,
    target: l.target,
    lineStyle: {
      color: 'rgba(0, 255, 136, 0.15)',
      width: 1,
      curveness: 0.1,
    },
    label: {
      show: false,
    },
  }))

  // 分类
  const categories = [
    { name: 'entity', itemStyle: { color: categoryColors['entity'] } },
    { name: 'concept', itemStyle: { color: categoryColors['concept'] } },
    { name: 'default', itemStyle: { color: categoryColors['default'] } },
  ]

  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15, 23, 42, 0.95)',
      borderColor: 'rgba(0, 255, 136, 0.3)',
      textStyle: { color: '#d4d4d4', fontSize: 12 },
      formatter: (params) => {
        if (params.dataType === 'node') {
          return `<b>${params.name}</b><br/>类型: ${params.data.category || '概念'}`
        }
        if (params.dataType === 'edge') {
          return `${params.data.source} → ${params.data.target}`
        }
        return ''
      },
    },
    series: [{
      type: 'graph',
      layout: 'force',
      animation: true,
      animationDuration: 1500,
      animationEasingUpdate: 'quinticInOut',
      data: nodes,
      links: links,
      categories: categories,
      roam: true,
      draggable: true,
      focusNodeAdjacency: true,
      emphasis: {
        focus: 'adjacency',
        itemStyle: {
          borderWidth: 3,
          borderColor: '#00ff88',
        },
        lineStyle: {
          width: 3,
          color: '#00ff88',
        },
      },
      force: {
        // 极高阻尼：friction 越小减速越快，默认 0.6，设 0.1 迅速刹车
        friction: 0.1,
        // 增强向心引力，把孤岛拉回中心
        gravity: 0.2,
        // 固定边长，凝聚核心星系
        edgeLength: 50,
        // 排斥力
        repulsion: 200,
        // 布局动画（3秒后强制关闭）
        layoutAnimation: true,
      },
      label: {
        position: 'right',
        formatter: '{b}',
      },
      lineStyle: {
        opacity: 0.6,
        curveness: 0.1,
      },
    }],
  }
}

async function initChart() {
  if (!chartRef.value) return

  // 初始化 ECharts
  chartInstance = echarts.init(chartRef.value, null, { renderer: 'canvas' })

  // 显示加载动画
  chartInstance.showLoading({
    text: '正在加载知识图谱...',
    color: '#00ff88',
    textColor: '#d4d4d4',
    maskColor: 'rgba(15, 23, 42, 0.8)',
  })

  // 获取数据
  const graphData = await fetchGraphData()

  if (!graphData || !graphData.nodes || graphData.nodes.length === 0) {
    chartInstance.hideLoading()
    // 显示空状态
    chartInstance.setOption({
      title: {
        text: '暂无图谱数据',
        subtext: '上传文档后，AI 将自动构建知识图谱',
        left: 'center',
        top: 'center',
        textStyle: { color: '#6b7280', fontSize: 16 },
        subtextStyle: { color: '#4b5563', fontSize: 12 },
      },
    })
    return
  }

  const option = buildEChartsOption(graphData)
  chartInstance.hideLoading()
  chartInstance.setOption(option)

  // 3 秒后强制关闭布局动画，彻底锁定节点坐标，阻止任何漂移
  layoutTimer = setTimeout(() => {
    if (chartInstance) {
      chartInstance.setOption({
        series: [{
          force: {
            layoutAnimation: false,
          },
        }],
      })
    }
  }, 3000)
}

function handleResize() {
  if (chartInstance) {
    chartInstance.resize()
  }
}

// 监听 visible 变化
watch(() => props.visible, async (val) => {
  if (val) {
    await nextTick()
    setTimeout(initChart, 150)
  } else {
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
    if (layoutTimer) {
      clearTimeout(layoutTimer)
      layoutTimer = null
    }
  }
})

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  if (layoutTimer) {
    clearTimeout(layoutTimer)
    layoutTimer = null
  }
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
          <div ref="chartRef" class="w-full h-full"></div>

          <div class="absolute top-3 left-4 space-y-1">
            <div class="flex items-center gap-2 text-[10px]">
              <span class="w-2 h-2 rounded-full bg-[#00ff88]"></span>
              <span class="text-geek-text-dim">实体</span>
              <span class="w-2 h-2 rounded-full bg-[#7c3aed]"></span>
              <span class="text-geek-text-dim">概念</span>
              <span class="w-2 h-2 rounded-full bg-[#06b6d4]"></span>
              <span class="text-geek-text-dim">其他</span>
            </div>
          </div>
        </div>

        <div class="px-5 py-3 border-t border-geek-border shrink-0">
          <div class="text-[10px] text-geek-text-dim">⚡ 知识图谱由 Neo4j 驱动，节点随文档上传自动生长。支持拖拽、缩放和点击聚焦。</div>
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
