<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { VueFlow, Position, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { getLayoutedElements } from '../utils/elkLayout.js'

const props = defineProps({
  visible: Boolean,
  graphData: {
    type: Object,
    default: () => ({ nodes: [], edges: [] })
  },
  isLoading: Boolean,
  activeNodeId: {
    type: String,
    default: null,
  },
})
const emit = defineEmits(['close', 'nodeClick', 'analyze'])

const layoutLoading = ref(false)
const error = ref(null)
const flowNodes = ref([])
const flowEdges = ref([])
const selectedNode = ref(null)
const searchQuery = ref('')
const hasData = ref(false)

// ── Path Finder 状态 ──
const selectedPathNodes = ref([])   // 最多 2 个 nodeId：[起点, 终点]
const highlightedPath = ref({ nodeIds: new Set(), edgeIds: new Set() })

// ── Diff Mode 状态 ──
const isDiffMode = ref(false)

const isAnalyzing = computed(() => props.isLoading || layoutLoading.value)

const CYBER_PALETTE = [
  {
    name: 'cyber-blue',
    bg: 'linear-gradient(135deg, rgba(30,58,138,0.50) 0%, rgba(30,64,175,0.35) 100%)',
    border: '#60a5fa', borderHover: '#93c5fd', text: '#bfdbfe',
    glow: '0 0 16px rgba(96,165,250,0.20), inset 0 1px 0 rgba(96,165,250,0.10)',
    glowHover: '0 0 24px rgba(96,165,250,0.35), 0 0 48px rgba(96,165,250,0.12), inset 0 1px 0 rgba(96,165,250,0.15)',
    miniMap: '#3b82f6',
  },
  {
    name: 'neon-purple',
    bg: 'linear-gradient(135deg, rgba(88,28,135,0.50) 0%, rgba(107,33,168,0.35) 100%)',
    border: '#c084fc', borderHover: '#d8b4fe', text: '#e9d5ff',
    glow: '0 0 16px rgba(192,132,252,0.18), inset 0 1px 0 rgba(192,132,252,0.08)',
    glowHover: '0 0 24px rgba(192,132,252,0.35), 0 0 48px rgba(192,132,252,0.12), inset 0 1px 0 rgba(192,132,252,0.12)',
    miniMap: '#a855f7',
  },
  {
    name: 'emerald-green',
    bg: 'linear-gradient(135deg, rgba(6,78,59,0.50) 0%, rgba(4,120,87,0.35) 100%)',
    border: '#34d399', borderHover: '#6ee7b7', text: '#a7f3d0',
    glow: '0 0 16px rgba(52,211,153,0.18), inset 0 1px 0 rgba(52,211,153,0.08)',
    glowHover: '0 0 24px rgba(52,211,153,0.35), 0 0 48px rgba(52,211,153,0.12), inset 0 1px 0 rgba(52,211,153,0.12)',
    miniMap: '#10b981',
  },
  {
    name: 'amber-gold',
    bg: 'linear-gradient(135deg, rgba(113,63,18,0.50) 0%, rgba(146,64,14,0.35) 100%)',
    border: '#fbbf24', borderHover: '#fcd34d', text: '#fef3c7',
    glow: '0 0 16px rgba(251,191,36,0.18), inset 0 1px 0 rgba(251,191,36,0.08)',
    glowHover: '0 0 24px rgba(251,191,36,0.35), 0 0 48px rgba(251,191,36,0.12), inset 0 1px 0 rgba(251,191,36,0.12)',
    miniMap: '#f59e0b',
  },
  {
    name: 'coral-red',
    bg: 'linear-gradient(135deg, rgba(127,29,29,0.50) 0%, rgba(153,27,27,0.35) 100%)',
    border: '#f87171', borderHover: '#fca5a5', text: '#fee2e2',
    glow: '0 0 16px rgba(248,113,113,0.18), inset 0 1px 0 rgba(248,113,113,0.08)',
    glowHover: '0 0 24px rgba(248,113,113,0.35), 0 0 48px rgba(248,113,113,0.12), inset 0 1px 0 rgba(248,113,113,0.12)',
    miniMap: '#ef4444',
  },
  {
    name: 'indigo-deep',
    bg: 'linear-gradient(135deg, rgba(30,27,75,0.50) 0%, rgba(49,46,129,0.35) 100%)',
    border: '#818cf8', borderHover: '#a5b4fc', text: '#e0e7ff',
    glow: '0 0 16px rgba(129,140,248,0.20), inset 0 1px 0 rgba(129,140,248,0.10)',
    glowHover: '0 0 24px rgba(129,140,248,0.35), 0 0 48px rgba(129,140,248,0.12), inset 0 1px 0 rgba(129,140,248,0.15)',
    miniMap: '#6366f1',
  },
  {
    name: 'violet-bloom',
    bg: 'linear-gradient(135deg, rgba(88,28,135,0.45) 0%, rgba(124,58,237,0.30) 100%)',
    border: '#a78bfa', borderHover: '#c4b5fd', text: '#ddd6fe',
    glow: '0 0 16px rgba(167,139,250,0.20), inset 0 1px 0 rgba(167,139,250,0.10)',
    glowHover: '0 0 24px rgba(167,139,250,0.35), 0 0 48px rgba(167,139,250,0.12), inset 0 1px 0 rgba(167,139,250,0.15)',
    miniMap: '#8b5cf6',
  },
  {
    name: 'teal-cyan',
    bg: 'linear-gradient(135deg, rgba(6,78,59,0.45) 0%, rgba(4,120,87,0.30) 100%)',
    border: '#2dd4bf', borderHover: '#5eead4', text: '#ccfbf1',
    glow: '0 0 16px rgba(45,212,191,0.18), inset 0 1px 0 rgba(45,212,191,0.08)',
    glowHover: '0 0 24px rgba(45,212,191,0.35), 0 0 48px rgba(45,212,191,0.12), inset 0 1px 0 rgba(45,212,191,0.12)',
    miniMap: '#14b8a6',
  },
  {
    name: 'orange-blaze',
    bg: 'linear-gradient(135deg, rgba(113,63,18,0.45) 0%, rgba(180,83,9,0.30) 100%)',
    border: '#fb923c', borderHover: '#fdba74', text: '#ffedd5',
    glow: '0 0 16px rgba(251,146,60,0.18), inset 0 1px 0 rgba(251,146,60,0.08)',
    glowHover: '0 0 24px rgba(251,146,60,0.35), 0 0 48px rgba(251,146,60,0.12), inset 0 1px 0 rgba(251,146,60,0.12)',
    miniMap: '#f97316',
  },
  {
    name: 'rose-pink',
    bg: 'linear-gradient(135deg, rgba(136,19,55,0.45) 0%, rgba(159,18,57,0.30) 100%)',
    border: '#fb7185', borderHover: '#fda4af', text: '#ffe4e6',
    glow: '0 0 16px rgba(251,113,133,0.18), inset 0 1px 0 rgba(251,113,133,0.08)',
    glowHover: '0 0 24px rgba(251,113,133,0.35), 0 0 48px rgba(251,113,133,0.12), inset 0 1px 0 rgba(251,113,133,0.12)',
    miniMap: '#f43f5e',
  },
  {
    name: 'sky-frost',
    bg: 'linear-gradient(135deg, rgba(12,74,110,0.45) 0%, rgba(8,145,178,0.30) 100%)',
    border: '#22d3ee', borderHover: '#67e8f9', text: '#cffafe',
    glow: '0 0 16px rgba(34,211,238,0.18), inset 0 1px 0 rgba(34,211,238,0.08)',
    glowHover: '0 0 24px rgba(34,211,238,0.35), 0 0 48px rgba(34,211,238,0.12), inset 0 1px 0 rgba(34,211,238,0.12)',
    miniMap: '#06b6d4',
  },
  {
    name: 'geek-gray',
    bg: 'linear-gradient(135deg, rgba(31,41,55,0.60) 0%, rgba(55,65,81,0.40) 100%)',
    border: '#6b7280', borderHover: '#9ca3af', text: '#d1d5db',
    glow: '0 0 12px rgba(107,114,128,0.12), inset 0 1px 0 rgba(107,114,128,0.06)',
    glowHover: '0 0 20px rgba(107,114,128,0.25), inset 0 1px 0 rgba(107,114,128,0.10)',
    miniMap: '#6b7280',
  },
]

const SEMANTIC_LAYER_MAP = {
  api: 0,
  api_client: 0,
  controller: 0,
  router: 0,
  route: 0,
  endpoint: 0,
  gateway: 0,
  handler: 0,
  resource: 0,
  business: 2,
  service: 2,
  manager: 2,
  impl: 2,
  processor: 2,
  orchestrator: 2,
  logic: 8,
  usecase: 2,
  command: 2,
  query: 2,
  data: 1,
  repository: 1,
  dao: 1,
  mapper: 1,
  db: 1,
  database: 1,
  persistence: 1,
  domain: 3,
  entity: 3,
  model: 3,
  dto: 3,
  vo: 3,
  record: 3,
  infrastructure: 11,
  config: 11,
  util: 11,
  helper: 11,
  middleware: 11,
  ui_page: 6,
  page: 6,
  view: 6,
  screen: 6,
  layout: 6,
  ui_component: 7,
  component: 7,
  widget: 7,
  state: 5,
  store: 5,
  pinia: 5,
  redux: 5,
  vuex: 5,
}

const UNKNOWN_PALETTE_INDEX = 11

function hashLayerToPalette(layer) {
  let hash = 0
  for (let i = 0; i < layer.length; i++) {
    hash = ((hash << 5) - hash + layer.charCodeAt(i)) | 0
  }
  return Math.abs(hash) % CYBER_PALETTE.length
}

const _layerStyleCache = new Map()

function resolveLayerStyle(layer) {
  if (!layer || layer === 'unknown') {
    return { ...CYBER_PALETTE[UNKNOWN_PALETTE_INDEX], label: '' }
  }
  if (_layerStyleCache.has(layer)) {
    return _layerStyleCache.get(layer)
  }
  let paletteIndex = SEMANTIC_LAYER_MAP[layer]
  if (paletteIndex === undefined) {
    const lower = layer.toLowerCase()
    for (const [key, idx] of Object.entries(SEMANTIC_LAYER_MAP)) {
      if (lower.includes(key)) {
        paletteIndex = idx
        break
      }
    }
  }
  if (paletteIndex === undefined) {
    paletteIndex = hashLayerToPalette(layer)
  }
  const palette = CYBER_PALETTE[paletteIndex]
  const label = layer.replace(/_/g, ' ').toUpperCase()
  const style = { ...palette, label }
  _layerStyleCache.set(layer, style)
  return style
}

function getLayerStyle(layer) {
  return resolveLayerStyle(layer)
}

const NODE_TYPE_ICONS = { File: '📄', Class: '📦', Function: '⚡' }
const NODE_TYPE_BADGES = { File: 'File', Class: 'Class', Function: 'Fn' }

const EDGE_CONFIG = {
  CONTAINS: { color: '#475569', width: 1, dash: '6 4', animated: false, label: 'contains' },
  IMPORTS:  { color: '#f59e0b', width: 1.5, dash: null, animated: false, label: 'imports' },
  CALLS:    { color: '#34d399', width: 2, dash: null, animated: true, label: 'calls' },
}

function mapBackendToVueFlow(backendData) {
  if (!backendData?.nodes?.length) return { nodes: [], edges: [] }

  const vfNodes = backendData.nodes.map((n) => {
    const layer = n.layer || 'unknown'
    const layerStyle = resolveLayerStyle(layer)
    const nodeType = n.type || 'Function'
    return {
      id: n.id,
      type: nodeType === 'File' ? 'file' : nodeType === 'Class' ? 'classNode' : 'funcNode',
      position: { x: 0, y: 0 },
      data: {
        label: n.name || n.id,
        nodeType,
        layer,
        layerLabel: layerStyle.label,
        icon: NODE_TYPE_ICONS[nodeType] || '📍',
        badge: NODE_TYPE_BADGES[nodeType] || 'Node',
        color: layerStyle.text,
        filePath: n.file_path || '',
        diffStatus: n.diff_status || null,
        extra: n,
      },
      style: {
        width: (nodeType === 'File' ? 260 : nodeType === 'Class' ? 200 : 180) + 'px',
        height: (nodeType === 'File' ? 56 : nodeType === 'Class' ? 44 : 40) + 'px',
      },
      sourcePosition: Position.RIGHT,
      targetPosition: Position.LEFT,
    }
  })

  const validIds = new Set(backendData.nodes.map((n) => n.id))
  const vfEdges = (backendData.edges || [])
    .filter((e) => validIds.has(e.source) && validIds.has(e.target))
    .map((e, i) => {
      const cfg = EDGE_CONFIG[e.type] || EDGE_CONFIG.CONTAINS
      return {
        id: e.id || `e-${i}`,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
        animated: cfg.animated,
        diffStatus: e.diff_status || null,
        style: {
          stroke: cfg.color,
          strokeWidth: cfg.width,
          strokeDasharray: cfg.dash || undefined,
        },
        label: e.type !== 'CONTAINS' ? cfg.label : undefined,
        labelStyle: { fill: cfg.color, fontSize: '9px', fontWeight: 600, fontFamily: "'JetBrains Mono', monospace" },
        labelBgStyle: { fill: '#0a0a0a', stroke: cfg.color, strokeWidth: 0.5, fillOpacity: 0.9 },
        labelBgPadding: [4, 6],
        labelBgBorderRadius: 3,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: cfg.color,
          width: 12,
          height: 12,
        },
      }
    })

  return { nodes: vfNodes, edges: vfEdges }
}

async function processGraph() {
  if (!props.graphData?.nodes?.length) return

  layoutLoading.value = true
  error.value = null

  try {
    const { nodes: rawNodes, edges: rawEdges } = mapBackendToVueFlow(props.graphData)
    const { nodes: layouted, edges } = await getLayoutedElements(rawNodes, rawEdges)

    flowNodes.value = []
    flowEdges.value = []
    await nextTick()

    flowNodes.value = layouted
    flowEdges.value = edges
    hasData.value = true
  } catch (err) {
    console.error('[CodeGraphViewer] layout failed:', err)
    error.value = err.message
  } finally {
    layoutLoading.value = false
  }
}

watch(() => props.graphData, (newVal) => {
  if (props.visible && newVal?.nodes?.length) {
    nextTick(() => processGraph())
  }
}, { deep: true })

watch(() => props.visible, (v) => {
  if (v && props.graphData?.nodes?.length && !hasData.value) {
    nextTick(() => processGraph())
  }
})

function handleAnalyze() {
  emit('analyze')
}

const stats = computed(() => {
  const nodes = props.graphData?.nodes || []
  const edges = props.graphData?.edges || []
  const byType = {}
  for (const n of nodes) byType[n.type] = (byType[n.type] || 0) + 1
  const byEdge = {}
  for (const e of edges) byEdge[e.type] = (byEdge[e.type] || 0) + 1
  return { totalNodes: nodes.length, totalEdges: edges.length, byType, byEdge }
})

const layerStats = computed(() => {
  const nodes = props.graphData?.nodes || []
  const byLayer = {}
  for (const n of nodes) {
    const layer = n.layer || 'unknown'
    byLayer[layer] = (byLayer[layer] || 0) + 1
  }
  return byLayer
})

const activeLayerStyles = computed(() => {
  const styles = {}
  for (const layer of Object.keys(layerStats.value)) {
    styles[layer] = resolveLayerStyle(layer)
  }
  return styles
})

const filteredNodes = computed(() => {
  if (!searchQuery.value) return flowNodes.value
  const q = searchQuery.value.toLowerCase()
  return flowNodes.value.filter((n) => {
    const label = (n.data?.label || '').toLowerCase()
    const nodeType = (n.data?.nodeType || '').toLowerCase()
    return label.includes(q) || nodeType.includes(q)
  })
})

const filteredNodeIds = computed(() => new Set(filteredNodes.value.map((n) => n.id)))

const hasHighlightedPath = computed(() => highlightedPath.value.nodeIds.size > 0)

const hasDiffData = computed(() => {
  return flowNodes.value.some((n) => n.data?.diffStatus) ||
         flowEdges.value.some((e) => e.diffStatus)
})

// ── Diff Mode 样式映射 ──
const DIFF_NODE_CLASS = {
  added: 'diff-added',
  modified: 'diff-modified',
  impacted: 'diff-impacted',
  deleted: 'diff-deleted',
  unchanged: 'diff-unchanged',
}

const DIFF_EDGE_STYLES = {
  added:    { stroke: '#22c55e', strokeWidth: 2.5 },
  modified: { stroke: '#facc15', strokeWidth: 2.5 },
  impacted: { stroke: '#f97316', strokeWidth: 2, strokeDasharray: '6 3' },
  deleted:  { stroke: '#ef4444', strokeWidth: 1.5, strokeDasharray: '4 4' },
}

const DIFF_MARKER_COLORS = {
  added: '#22c55e',
  modified: '#facc15',
  impacted: '#f97316',
  deleted: '#ef4444',
}

const displayNodes = computed(() => {
  const ids = filteredNodeIds.value
  const pathNodeIds = highlightedPath.value.nodeIds
  const pathActive = pathNodeIds.size > 0
  const dm = isDiffMode.value

  return flowNodes.value
    .filter((n) => ids.has(n.id))
    .map((n) => {
      const isOnPath = pathActive && pathNodeIds.has(n.id)
      const isEndpoint = selectedPathNodes.value.includes(n.id)
      const ds = n.data?.diffStatus
      const diffClass = dm && ds ? DIFF_NODE_CLASS[ds] || '' : ''
      const diffDimClass = dm && !ds ? 'diff-unchanged' : ''

      return {
        ...n,
        class: [
          pathActive && !isOnPath ? 'path-dimmed' : '',
          isOnPath ? 'path-node-active' : '',
          isEndpoint ? 'path-endpoint' : '',
          dm ? diffClass || diffDimClass : '',
        ].filter(Boolean).join(' '),
      }
    })
})

const displayEdges = computed(() => {
  const ids = filteredNodeIds.value
  const pathEdgeIds = highlightedPath.value.edgeIds
  const pathNodeIds = highlightedPath.value.nodeIds
  const pathActive = pathNodeIds.size > 0
  const dm = isDiffMode.value

  return flowEdges.value
    .filter((e) => ids.has(e.source) && ids.has(e.target))
    .map((e) => {
      const isOnPath = pathActive && pathEdgeIds.has(e.id)
      const ds = e.diffStatus

      // Diff Mode 边样式
      let diffStyle = null
      let diffClass = ''
      let diffMarker = null
      if (dm && ds && DIFF_EDGE_STYLES[ds]) {
        diffStyle = DIFF_EDGE_STYLES[ds]
        diffClass = `diff-edge-${ds}`
        diffMarker = { type: MarkerType.ArrowClosed, color: DIFF_MARKER_COLORS[ds], width: 14, height: 14 }
      } else if (dm && !ds) {
        diffClass = 'diff-edge-unchanged'
      }

      // Path Finder 优先级高于 Diff Mode
      if (isOnPath) {
        return {
          ...e,
          animated: true,
          class: ['path-edge-glow', diffClass].filter(Boolean).join(' '),
          style: { stroke: '#ef4444', strokeWidth: 3 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444', width: 14, height: 14 },
        }
      }

      if (pathActive) {
        return {
          ...e,
          class: ['path-edge-dimmed', diffClass].filter(Boolean).join(' '),
          style: { ...e.style, opacity: 0.15 },
          markerEnd: e.markerEnd,
        }
      }

      // Diff Mode 样式
      if (dm && diffStyle) {
        return {
          ...e,
          animated: ds === 'added' || ds === 'modified',
          class: diffClass,
          style: diffStyle,
          markerEnd: diffMarker || e.markerEnd,
          label: ds === 'impacted' ? '⚠ impacted' : e.label,
          labelStyle: ds === 'impacted'
            ? { fill: '#f97316', fontSize: '9px', fontWeight: 700, fontFamily: "'JetBrains Mono', monospace" }
            : e.labelStyle,
          labelBgStyle: ds === 'impacted'
            ? { fill: '#0a0a0a', stroke: '#f97316', strokeWidth: 0.5, fillOpacity: 0.9 }
            : e.labelBgStyle,
          labelBgPadding: [4, 6],
          labelBgBorderRadius: 3,
        }
      }

      return {
        ...e,
        class: diffClass,
      }
    })
})

function handleNodeClick(event) {
  selectedNode.value = event.node?.data?.extra || null
  emit('nodeClick', event.node?.data?.extra)
}

// ── Path Finder: BFS 最短有向路径 ──
function findShortestPath(sourceId, targetId, edges) {
  if (sourceId === targetId) return { nodeIds: [sourceId], edgeIds: [] }

  // 构建邻接表: source → [{ target, edgeId }]
  const adj = new Map()
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, [])
    adj.get(e.source).push({ target: e.target, edgeId: e.id })
  }

  // BFS
  const visited = new Set([sourceId])
  const queue = [[sourceId, [sourceId], []]] // [currentNode, pathNodes, pathEdges]

  while (queue.length > 0) {
    const [current, pathNodes, pathEdges] = queue.shift()
    const neighbors = adj.get(current) || []

    for (const { target, edgeId } of neighbors) {
      if (target === targetId) {
        return { nodeIds: [...pathNodes, target], edgeIds: [...pathEdges, edgeId] }
      }
      if (!visited.has(target)) {
        visited.add(target)
        queue.push([target, [...pathNodes, target], [...pathEdges, edgeId]])
      }
    }
  }

  return null // 不可达
}

function handlePathNodeClick(event) {
  const nodeId = event.node?.id
  if (!nodeId) return

  const isShift = event.event?.shiftKey

  if (!isShift) {
    // 普通点击：走原有逻辑
    selectedNode.value = event.node?.data?.extra || null
    emit('nodeClick', event.node?.data?.extra)
    return
  }

  // Shift + Click: Path Finder 逻辑
  if (selectedPathNodes.value.length >= 2) {
    // 已满 2 个，重置
    selectedPathNodes.value = [nodeId]
    highlightedPath.value = { nodeIds: new Set(), edgeIds: new Set() }
    return
  }

  selectedPathNodes.value.push(nodeId)

  if (selectedPathNodes.value.length === 2) {
    // 选满 2 个，触发寻路
    const [source, target] = selectedPathNodes.value
    const result = findShortestPath(source, target, flowEdges.value)
    if (result) {
      highlightedPath.value = { nodeIds: new Set(result.nodeIds), edgeIds: new Set(result.edgeIds) }
    } else {
      highlightedPath.value = { nodeIds: new Set(), edgeIds: new Set() }
    }
  }
}

function clearPathFinder() {
  selectedPathNodes.value = []
  highlightedPath.value = { nodeIds: new Set(), edgeIds: new Set() }
}

function handlePaneClick() {
  selectedNode.value = null
  clearPathFinder()
}

const isNodeActive = (nodeId) => {
  if (!props.activeNodeId) return true
  return nodeId === props.activeNodeId
}

const isNodeHighlighted = (nodeId) => {
  return props.activeNodeId && nodeId === props.activeNodeId
}

// ── Diff Mode: 节点 Tailwind class 计算 ──
function getDiffNodeClasses(diffStatus) {
  if (!isDiffMode.value) return ''
  switch (diffStatus) {
    case 'added':
      return 'ring-2 ring-green-500 shadow-[0_0_15px_rgba(34,197,94,0.6)]'
    case 'modified':
      return 'ring-2 ring-yellow-400 shadow-[0_0_15px_rgba(250,204,21,0.6)] animate-pulse'
    case 'impacted':
      return 'border-dashed border-2 border-orange-500 opacity-80'
    case 'deleted':
      return 'ring-2 ring-red-500 opacity-40 grayscale line-through'
    default:
      return 'opacity-20 grayscale'
  }
}
</script>

<template>
  <!-- Diff Mode Toggle - fixed 定位，脱离所有嵌套，z-index 最大值 -->
  <button
    v-if="visible"
    @click="isDiffMode = !isDiffMode"
    style="position: fixed; top: 80px; right: 30px; z-index: 2147483647;"
    :class="isDiffMode ? 'bg-orange-600 border-orange-500 shadow-[0_0_20px_rgba(234,88,12,0.9)]' : 'bg-gray-800 border-gray-600'"
    class="px-4 py-2 rounded-lg border text-white font-bold transition-all duration-300 cursor-pointer hover:scale-110"
  >
    {{ isDiffMode ? '🔥 Diff模式: 开启' : '👁️ Diff模式: 关闭' }}
  </button>

  <Transition name="graph-slide">
    <div v-if="visible" class="fixed inset-0 z-[100] flex flex-col" @click.self="emit('close')">
      <div class="absolute inset-0 bg-black/80 backdrop-blur-sm"></div>

      <div class="relative w-full h-full flex flex-col"
        style="background: #060a12">

        <div class="flex items-center justify-between px-5 py-3 border-b border-slate-700/60 shrink-0 bg-black/30">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-emerald-900/40 border border-emerald-500/30 flex items-center justify-center text-sm">🏗️</div>
            <div>
              <div class="text-sm font-bold text-emerald-400 tracking-wide">Code Graph Viewer</div>
              <div class="text-[10px] text-slate-500">ELK Layered · Orthogonal · Cross-file Dependency</div>
            </div>
          </div>

          <div class="flex items-center gap-3">
            <div class="relative">
              <input
                v-model="searchQuery"
                placeholder="搜索节点..."
                class="w-36 px-2.5 py-1 text-[11px] bg-slate-900/80 border border-slate-700/60 rounded-md text-slate-300 placeholder-slate-600 focus:outline-none focus:border-emerald-500/50 transition-colors"
              />
            </div>
            <button @click="emit('close')" class="text-slate-500 hover:text-slate-300 text-lg leading-none transition-colors">×</button>
          </div>
        </div>

        <div class="flex-1 min-h-0 relative w-full h-full">

          <button
            @click="emit('close')"
            class="absolute top-6 left-6 z-50 flex items-center gap-2 px-4 py-2 bg-gray-800/80 backdrop-blur border border-gray-600 rounded-lg hover:bg-gray-700 text-gray-200 shadow-lg transition-colors font-mono text-sm"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            <span>返回代码</span>
          </button>

          <!-- 右上角按钮组 -->
          <div class="absolute right-4 top-4 z-50 flex items-center gap-2">
            <button
              v-if="!isAnalyzing"
              @click="handleAnalyze"
              class="flex items-center gap-2 bg-gray-800/60 backdrop-blur-md border border-gray-700 text-gray-300 hover:text-white hover:bg-gray-700/80 px-4 py-2 rounded-lg text-sm font-medium transition-all shadow-xl font-mono"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="2" />
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
              <span>解析项目架构</span>
            </button>

            <button
              v-if="isAnalyzing"
              disabled
              class="flex items-center gap-2 bg-gray-800/40 backdrop-blur-md border border-gray-700/50 text-gray-400 px-4 py-2 rounded-lg text-sm font-medium shadow-xl cursor-not-allowed font-mono"
            >
              <span class="analyze-spinner-sm"></span>
              <span>解析中...</span>
            </button>
          </div>

          <div v-if="isAnalyzing" class="absolute inset-0 flex items-center justify-center z-20 bg-[#060a12]/90">
            <div class="text-center">
              <div class="scan-loader mb-5">
                <div class="scan-hex">
                  <div class="scan-hex-ring"></div>
                  <div class="scan-hex-ring scan-ring-2"></div>
                  <div class="scan-hex-core"></div>
                </div>
                <div class="scan-line"></div>
              </div>
              <div class="text-xs text-emerald-400 font-semibold tracking-wider mb-1">
                {{ props.isLoading ? '扫描项目文件中...' : 'ELK 正交布局计算中...' }}
              </div>
              <div class="text-[10px] text-slate-600">
                {{ props.isLoading ? 'AST Extraction · Symbol Resolution' : 'Layered Algorithm · Orthogonal Edge Routing' }}
              </div>
              <div class="mt-3 flex justify-center gap-1">
                <span class="scan-dot" style="animation-delay: 0s"></span>
                <span class="scan-dot" style="animation-delay: 0.2s"></span>
                <span class="scan-dot" style="animation-delay: 0.4s"></span>
              </div>
            </div>
          </div>

          <div v-if="error && !isAnalyzing" class="absolute inset-0 flex items-center justify-center z-20 bg-[#060a12]/85">
            <div class="text-center max-w-[80%]">
              <div class="text-red-400 text-xl mb-2">⚠️</div>
              <div class="text-xs text-red-300 mb-2">布局计算失败</div>
              <div class="text-[10px] text-slate-500 break-all">{{ error }}</div>
            </div>
          </div>

          <div v-if="!hasData && !isAnalyzing" class="absolute inset-0 flex items-center justify-center z-20">
            <div class="text-center">
              <div class="empty-hex mb-4">
                <svg width="80" height="80" viewBox="0 0 80 80">
                  <polygon points="40,4 72,22 72,58 40,76 8,58 8,22"
                    fill="none" stroke="#1e293b" stroke-width="1.5"
                    stroke-dasharray="4 3" />
                  <text x="40" y="44" text-anchor="middle" fill="#334155" font-size="22">🏗️</text>
                </svg>
              </div>
              <div class="text-xs text-slate-500 mb-2">暂无架构数据</div>
              <div class="text-[10px] text-slate-600 mb-4">点击上方按钮解析项目架构</div>
              <button
                @click="handleAnalyze"
                :disabled="isAnalyzing"
                class="flex items-center gap-2 bg-gray-800/60 backdrop-blur-md border border-gray-700 text-gray-300 hover:text-white hover:bg-gray-700/80 px-5 py-2.5 rounded-lg text-sm font-medium transition-all shadow-xl font-mono"
              >
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="2" />
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                </svg>
                <span>解析项目架构</span>
              </button>
            </div>
          </div>

          <VueFlow
            v-if="flowNodes.length"
            :nodes="displayNodes"
            :edges="displayEdges"
            :fit-view-on-init="true"
            :default-viewport="{ zoom: 0.65, x: 0, y: 0 }"
            :min-zoom="0.08"
            :max-zoom="4"
            :nodes-draggable="true"
            :nodes-connectable="false"
            :elements-selectable="true"
            class="code-graph-flow w-full h-full"
            @node-click="handlePathNodeClick"
            @pane-click="handlePaneClick"
          >
            <Background :gap="24" :size="1" pattern-color="#333" />
            <Controls
              position="bottom-left"
              class="!bg-slate-900/90 !border-slate-700/50 !rounded-lg !shadow-xl"
            />
            <MiniMap
              position="bottom-right"
              :node-color="(n) => getLayerStyle(n.data?.layer).miniMap"
              :mask-color="'rgba(0,0,0,0.75)'"
              class="!bg-slate-900/90 !border-slate-700/50 !rounded-lg"
              :pannable="true"
              :zoomable="true"
            />

            <template #node-file="nodeProps">
              <div
                class="graph-file-node rounded-lg backdrop-blur-md shadow-lg"
                :class="[
                  !isNodeActive(nodeProps.id) && !hasHighlightedPath && !isDiffMode ? 'node-dimmed' : '',
                  isNodeHighlighted(nodeProps.id) ? 'node-highlighted' : '',
                  getDiffNodeClasses(nodeProps.data?.diffStatus),
                ]"
                :style="{
                  background: getLayerStyle(nodeProps.data?.layer).bg,
                  border: isNodeHighlighted(nodeProps.id)
                    ? '2px solid ' + getLayerStyle(nodeProps.data?.layer).borderHover
                    : '1.5px solid ' + getLayerStyle(nodeProps.data?.layer).border,
                  boxShadow: isNodeHighlighted(nodeProps.id)
                    ? getLayerStyle(nodeProps.data?.layer).glowHover
                    : getLayerStyle(nodeProps.data?.layer).glow,
                }"
              >
                <!-- Diff Mode: deleted 红叉 -->
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'deleted'" class="diff-deleted-x">✕</div>
                <!-- Diff Mode: impacted 警告角标 -->
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'impacted'" class="diff-impacted-badge">⚠</div>
                <!-- Diff Mode: added 标签 -->
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'added'" class="diff-status-tag diff-tag-added">+ADDED</div>
                <!-- Diff Mode: modified 标签 -->
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'modified'" class="diff-status-tag diff-tag-modified">~MOD</div>
                <div v-if="nodeProps.data?.layerLabel" class="layer-tag" :style="{ color: getLayerStyle(nodeProps.data?.layer).border }">
                  {{ nodeProps.data.layerLabel }} LAYER
                </div>
                <div class="file-header">
                  <span class="file-icon">{{ nodeProps.data?.icon }}</span>
                  <span class="file-label" :style="{ color: getLayerStyle(nodeProps.data?.layer).text }">{{ nodeProps.data?.label }}</span>
                </div>
                <div v-if="nodeProps.data?.filePath" class="file-path">{{ nodeProps.data.filePath.split('/').pop() }}</div>
              </div>
            </template>

            <template #node-classNode="nodeProps">
              <div
                class="graph-class-node rounded-lg backdrop-blur-md shadow-lg"
                :class="[
                  !isNodeActive(nodeProps.id) && !hasHighlightedPath && !isDiffMode ? 'node-dimmed' : '',
                  isNodeHighlighted(nodeProps.id) ? 'node-highlighted' : '',
                  getDiffNodeClasses(nodeProps.data?.diffStatus),
                ]"
                :style="{
                  background: getLayerStyle(nodeProps.data?.layer).bg,
                  border: isNodeHighlighted(nodeProps.id)
                    ? '2px solid ' + getLayerStyle(nodeProps.data?.layer).borderHover
                    : '1px solid ' + getLayerStyle(nodeProps.data?.layer).border,
                  boxShadow: isNodeHighlighted(nodeProps.id)
                    ? getLayerStyle(nodeProps.data?.layer).glowHover
                    : getLayerStyle(nodeProps.data?.layer).glow,
                }"
              >
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'deleted'" class="diff-deleted-x">✕</div>
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'impacted'" class="diff-impacted-badge">⚠</div>
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'added'" class="diff-status-tag diff-tag-added">+ADDED</div>
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'modified'" class="diff-status-tag diff-tag-modified">~MOD</div>
                <div v-if="nodeProps.data?.layerLabel" class="layer-tag" :style="{ color: getLayerStyle(nodeProps.data?.layer).border }">
                  {{ nodeProps.data.layerLabel }} LAYER
                </div>
                <span class="node-icon">{{ nodeProps.data?.icon }}</span>
                <span class="node-label" :style="{ color: getLayerStyle(nodeProps.data?.layer).text }">{{ nodeProps.data?.label }}</span>
                <span class="node-badge" :style="{ color: getLayerStyle(nodeProps.data?.layer).border, background: getLayerStyle(nodeProps.data?.layer).border + '1a' }">{{ nodeProps.data?.badge }}</span>
              </div>
            </template>

            <template #node-funcNode="nodeProps">
              <div
                class="graph-func-node rounded-lg backdrop-blur-md shadow-lg"
                :class="[
                  !isNodeActive(nodeProps.id) && !hasHighlightedPath && !isDiffMode ? 'node-dimmed' : '',
                  isNodeHighlighted(nodeProps.id) ? 'node-highlighted' : '',
                  getDiffNodeClasses(nodeProps.data?.diffStatus),
                ]"
                :style="{
                  background: getLayerStyle(nodeProps.data?.layer).bg,
                  border: isNodeHighlighted(nodeProps.id)
                    ? '2px solid ' + getLayerStyle(nodeProps.data?.layer).borderHover
                    : '1px solid ' + getLayerStyle(nodeProps.data?.layer).border,
                  boxShadow: isNodeHighlighted(nodeProps.id)
                    ? getLayerStyle(nodeProps.data?.layer).glowHover
                    : getLayerStyle(nodeProps.data?.layer).glow,
                }"
              >
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'deleted'" class="diff-deleted-x">✕</div>
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'impacted'" class="diff-impacted-badge">⚠</div>
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'added'" class="diff-status-tag diff-tag-added">+ADD</div>
                <div v-if="isDiffMode && nodeProps.data?.diffStatus === 'modified'" class="diff-status-tag diff-tag-modified">~MOD</div>
                <div v-if="nodeProps.data?.layerLabel" class="layer-tag" :style="{ color: getLayerStyle(nodeProps.data?.layer).border }">
                  {{ nodeProps.data.layerLabel }} LAYER
                </div>
                <span class="node-icon">{{ nodeProps.data?.icon }}</span>
                <span class="node-label" :style="{ color: getLayerStyle(nodeProps.data?.layer).text }">{{ nodeProps.data?.label }}</span>
                <span class="node-badge" :style="{ color: getLayerStyle(nodeProps.data?.layer).border, background: getLayerStyle(nodeProps.data?.layer).border + '1a' }">{{ nodeProps.data?.badge }}</span>
              </div>
            </template>
          </VueFlow>

          <div class="absolute top-3 left-3 z-10 flex flex-col gap-1.5 pointer-events-none">
            <!-- Path Finder 提示条 -->
            <div v-if="selectedPathNodes.length > 0" class="flex items-center gap-2 text-[9px] bg-black/80 backdrop-blur-sm border border-red-500/40 rounded-md px-2.5 py-1.5 pointer-events-auto">
              <span class="text-red-400 font-bold tracking-wider">PATH</span>
              <span class="flex items-center gap-1">
                <span
                  v-for="(nid, idx) in selectedPathNodes"
                  :key="nid"
                  class="flex items-center gap-1"
                >
                  <span class="px-1.5 py-0.5 rounded bg-red-900/40 border border-red-500/50 text-red-300 font-mono text-[8px]">{{ flowNodes.find(n => n.id === nid)?.data?.label || nid }}</span>
                  <span v-if="idx === 0 && selectedPathNodes.length === 2" class="text-slate-500">→</span>
                </span>
              </span>
              <span v-if="selectedPathNodes.length === 1" class="text-slate-500">Shift+点击选择终点</span>
              <span v-if="selectedPathNodes.length === 2 && hasHighlightedPath" class="text-emerald-400">{{ highlightedPath.nodeIds.size }} 节点 · {{ highlightedPath.edgeIds.size }} 边</span>
              <span v-if="selectedPathNodes.length === 2 && !hasHighlightedPath" class="text-amber-400">不可达</span>
              <button @click="clearPathFinder" class="ml-1 text-slate-500 hover:text-red-400 transition-colors text-[10px]">✕</button>
            </div>

            <div class="flex items-center gap-2 text-[9px] bg-black/70 backdrop-blur-sm border border-slate-700/40 rounded-md px-2.5 py-1.5 pointer-events-auto flex-wrap">
              <template v-for="(style, layer) in activeLayerStyles" :key="layer">
                <span v-if="style.label" class="flex items-center gap-1">
                  <span class="w-2.5 h-2.5 rounded" :style="{ background: style.border + '40', border: '1px solid ' + style.border }"></span>
                  <span class="text-slate-400">{{ style.label }}</span>
                </span>
              </template>
            </div>
            <div class="flex items-center gap-3 text-[9px] bg-black/70 backdrop-blur-sm border border-slate-700/40 rounded-md px-2.5 py-1.5 pointer-events-auto">
              <span class="flex items-center gap-1"><span class="w-4 h-0 border-t-2 border-dashed border-slate-500"></span><span class="text-slate-400">contains</span></span>
              <span class="flex items-center gap-1"><span class="w-4 h-0 border-t-2 border-amber-400"></span><span class="text-slate-400">imports</span></span>
              <span class="flex items-center gap-1"><span class="w-4 h-0 border-t-2 border-emerald-400"></span><span class="text-slate-400">calls</span></span>
              <span class="text-slate-600">|</span>
              <span class="flex items-center gap-1"><kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">Shift</kbd><span class="text-slate-400">+点击寻路</span></span>
            </div>
          </div>
        </div>

        <div class="border-t border-slate-700/60 shrink-0 bg-black/30">
          <div v-if="selectedNode" class="px-5 py-3 flex items-start gap-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-[11px]">{{ NODE_TYPE_ICONS[selectedNode.type] || '📍' }}</span>
                <span class="text-xs font-bold" :style="{ color: getLayerStyle(selectedNode.layer).text }">{{ selectedNode.name }}</span>
                <span class="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-400">{{ selectedNode.type }}</span>
                <span v-if="getLayerStyle(selectedNode.layer).label" class="text-[9px] px-1.5 py-0.5 rounded border" :style="{ color: getLayerStyle(selectedNode.layer).border, background: getLayerStyle(selectedNode.layer).border + '1a', borderColor: getLayerStyle(selectedNode.layer).border + '40' }">{{ getLayerStyle(selectedNode.layer).label }}</span>
              </div>
              <div v-if="selectedNode.file_path" class="text-[10px] text-slate-500 truncate">{{ selectedNode.file_path }}</div>
              <div v-if="selectedNode.params?.length" class="text-[10px] text-slate-500 mt-0.5">
                <span class="text-slate-600">params:</span> {{ selectedNode.params.join(', ') }}
              </div>
              <div v-if="selectedNode.return_type" class="text-[10px] text-slate-500">
                <span class="text-slate-600">returns:</span> {{ selectedNode.return_type }}
              </div>
              <div v-if="selectedNode.methods?.length" class="text-[10px] text-slate-500 mt-0.5">
                <span class="text-slate-600">methods:</span> {{ selectedNode.methods.join(', ') }}
              </div>
            </div>
            <button @click="selectedNode = null" class="text-slate-500 hover:text-slate-300 text-xs transition-colors">×</button>
          </div>

          <div v-else class="px-5 py-2.5 flex items-center justify-between">
            <div class="flex items-center gap-4 text-[10px] text-slate-500">
              <span>📊 {{ stats.totalNodes }} nodes</span>
              <span>🔗 {{ stats.totalEdges }} edges</span>
              <template v-for="(count, layer) in layerStats" :key="layer">
                <span v-if="count && getLayerStyle(layer).label" class="flex items-center gap-1">
                  <span class="w-1.5 h-1.5 rounded-full" :style="{ background: getLayerStyle(layer).miniMap }"></span>
                  {{ count }} {{ getLayerStyle(layer).label }}
                </span>
              </template>
            </div>
            <div class="text-[9px] text-slate-600">ELK Layered → RIGHT · Orthogonal</div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.code-graph-flow :deep(.vue-flow__node) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
}

.code-graph-flow :deep(.vue-flow__node-file),
.code-graph-flow :deep(.vue-flow__node-classNode),
.code-graph-flow :deep(.vue-flow__node-funcNode) {
  padding: 0 !important;
  border-radius: inherit !important;
  border: none !important;
  background: transparent !important;
}

.code-graph-flow :deep(.vue-flow__edge-textbg) {
  rx: 3;
  ry: 3;
}

.code-graph-flow :deep(.vue-flow__controls) {
  border-radius: 8px;
  overflow: hidden;
}

.code-graph-flow :deep(.vue-flow__controls-button) {
  background: #0f172a;
  border-color: #334155;
  fill: #64748b;
  width: 28px;
  height: 28px;
}

.code-graph-flow :deep(.vue-flow__controls-button:hover) {
  background: #1e293b;
  fill: #34d399;
}

.code-graph-flow :deep(.vue-flow__minimap) {
  border-radius: 8px;
  overflow: hidden;
}

.analyze-spinner-sm {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(191, 219, 254, 0.3);
  border-top-color: #bfdbfe;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.scan-loader {
  position: relative;
  width: 100px;
  height: 100px;
  margin: 0 auto;
}

.scan-hex {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.scan-hex-ring {
  position: absolute;
  width: 80px;
  height: 80px;
  border: 1.5px solid #34d39940;
  clip-path: polygon(50% 0%, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%);
  animation: hex-rotate 4s linear infinite;
}

.scan-ring-2 {
  width: 60px;
  height: 60px;
  border-color: #06b6d440;
  animation-direction: reverse;
  animation-duration: 3s;
}

.scan-hex-core {
  width: 20px;
  height: 20px;
  background: #34d399;
  clip-path: polygon(50% 0%, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%);
  animation: core-pulse 1.5s ease-in-out infinite;
}

@keyframes hex-rotate {
  to { transform: rotate(360deg); }
}

@keyframes core-pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.1); }
}

.scan-line {
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, #34d39960, #34d399, #34d39960, transparent);
  animation: scan-sweep 2s ease-in-out infinite;
}

@keyframes scan-sweep {
  0% { top: 0; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { top: 100%; opacity: 0; }
}

.scan-dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #34d399;
  animation: dot-blink 1.2s ease-in-out infinite;
}

@keyframes dot-blink {
  0%, 100% { opacity: 0.2; }
  50% { opacity: 1; }
}

.graph-file-node {
  width: 100%;
  height: 100%;
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}

.layer-tag {
  position: absolute;
  top: 3px;
  left: 8px;
  font-size: 7px;
  opacity: 0.45;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  pointer-events: none;
  line-height: 1;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.file-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 12px 4px;
}

.file-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.file-label {
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.02em;
}

.file-path {
  padding: 0 12px 6px;
  font-size: 9px;
  color: #475569;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.graph-class-node,
.graph-func-node {
  width: 100%;
  height: 100%;
  border-radius: inherit;
  display: flex;
  align-items: center;
  padding: 0 10px;
  gap: 6px;
  white-space: nowrap;
  overflow: hidden;
  transition: filter 0.15s;
  position: relative;
}

.graph-class-node:hover,
.graph-func-node:hover {
  filter: brightness(1.25);
}

.node-dimmed {
  opacity: 0.25;
  transition: opacity 0.3s ease, filter 0.3s ease;
}

/* ── Path Finder: 路径高亮 ── */

/* 不在路径上的节点：灰化 + 低透明度 */
.path-dimmed {
  opacity: 0.15 !important;
  filter: grayscale(1) brightness(0.5);
  transition: opacity 0.4s ease, filter 0.4s ease;
}

/* 路径上的节点：高亮边框 + 呼吸灯 */
.path-node-active {
  opacity: 1 !important;
  filter: none !important;
  border-color: #ef4444 !important;
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.4), 0 0 24px rgba(239, 68, 68, 0.15) !important;
  animation: path-node-breathe 2s ease-in-out infinite;
}

/* 起点/终点：更强发光 */
.path-endpoint {
  border-color: #f97316 !important;
  box-shadow: 0 0 16px rgba(249, 115, 22, 0.5), 0 0 32px rgba(249, 115, 22, 0.2), 0 0 48px rgba(239, 68, 68, 0.1) !important;
  animation: path-endpoint-pulse 1.5s ease-in-out infinite;
}

@keyframes path-node-breathe {
  0%, 100% { box-shadow: 0 0 8px rgba(239, 68, 68, 0.3), 0 0 16px rgba(239, 68, 68, 0.1); }
  50% { box-shadow: 0 0 16px rgba(239, 68, 68, 0.5), 0 0 32px rgba(239, 68, 68, 0.2); }
}

@keyframes path-endpoint-pulse {
  0%, 100% { box-shadow: 0 0 12px rgba(249, 115, 22, 0.4), 0 0 24px rgba(249, 115, 22, 0.15); }
  50% { box-shadow: 0 0 20px rgba(249, 115, 22, 0.6), 0 0 40px rgba(249, 115, 22, 0.25), 0 0 60px rgba(239, 68, 68, 0.1); }
}

/* 路径上的边：深红发光 + 流动动画 */
.path-edge-glow {
  filter: drop-shadow(0 0 6px rgba(239, 68, 68, 0.6)) drop-shadow(0 0 12px rgba(239, 68, 68, 0.3));
}

/* 不在路径上的边：灰化 */
.path-edge-dimmed {
  opacity: 0.1;
  filter: grayscale(1);
  transition: opacity 0.4s ease, filter 0.4s ease;
}

/* Vue Flow 边的 SVG 样式覆盖 */
.code-graph-flow :deep(.vue-flow__edge.path-edge-glow .vue-flow__edge-path) {
  stroke: #ef4444 !important;
  stroke-width: 3px !important;
  filter: drop-shadow(0 0 8px #ef4444) drop-shadow(0 0 16px rgba(239, 68, 68, 0.4));
}

.code-graph-flow :deep(.vue-flow__edge.path-edge-dimmed .vue-flow__edge-path) {
  stroke: #334155 !important;
  stroke-width: 1px !important;
  opacity: 0.15;
}

/* ══════════════════════════════════════════════════════════
   Diff Mode: 变更影响分析视觉样式
   ══════════════════════════════════════════════════════════ */

/* ── 节点: added (新增) ── 绿色发光 */
.diff-added {
  border-color: #22c55e !important;
  box-shadow: 0 0 15px rgba(34, 197, 94, 0.6), 0 0 30px rgba(34, 197, 94, 0.2) !important;
  opacity: 1 !important;
  filter: none !important;
}

/* ── 节点: modified (修改) ── 黄色发光 + 呼吸灯 */
.diff-modified {
  border-color: #facc15 !important;
  box-shadow: 0 0 15px rgba(250, 204, 21, 0.6), 0 0 30px rgba(250, 204, 21, 0.2) !important;
  opacity: 1 !important;
  filter: none !important;
  animation: diff-modified-pulse 2s ease-in-out infinite;
}

@keyframes diff-modified-pulse {
  0%, 100% { box-shadow: 0 0 10px rgba(250, 204, 21, 0.4), 0 0 20px rgba(250, 204, 21, 0.15); }
  50% { box-shadow: 0 0 20px rgba(250, 204, 21, 0.7), 0 0 40px rgba(250, 204, 21, 0.3), 0 0 60px rgba(250, 204, 21, 0.1); }
}

/* ── 节点: impacted (被波及) ── 橙色虚线边框 */
.diff-impacted {
  border: 2px dashed #f97316 !important;
  opacity: 0.85 !important;
  filter: none !important;
  box-shadow: 0 0 10px rgba(249, 115, 22, 0.3) !important;
}

/* ── 节点: deleted (删除) ── 红色半透明 + 灰度 + 删除线 */
.diff-deleted {
  border-color: #ef4444 !important;
  opacity: 0.4 !important;
  filter: grayscale(1) !important;
  position: relative;
}
.diff-deleted .node-label,
.diff-deleted .file-label {
  text-decoration: line-through;
  text-decoration-color: #ef4444;
}

/* deleted 红叉角标 */
.diff-deleted-x {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 900;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.6);
  z-index: 10;
  line-height: 1;
}

/* impacted 警告角标 */
.diff-impacted-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  background: #0a0a0a;
  border: 1.5px solid #f97316;
  color: #f97316;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  box-shadow: 0 0 8px rgba(249, 115, 22, 0.5);
  z-index: 10;
  line-height: 1;
}

/* Diff 状态标签 */
.diff-status-tag {
  position: absolute;
  top: -8px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 7px;
  font-weight: 800;
  letter-spacing: 0.08em;
  padding: 1px 5px;
  border-radius: 3px;
  z-index: 10;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  line-height: 1.4;
}
.diff-tag-added {
  background: #22c55e;
  color: #052e16;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
}
.diff-tag-modified {
  background: #facc15;
  color: #422006;
  box-shadow: 0 0 8px rgba(250, 204, 21, 0.5);
}

/* ── 节点: unchanged (无变化) ── Diff Mode 下虚化 */
.diff-unchanged {
  opacity: 0.2 !important;
  filter: grayscale(0.8) brightness(0.6);
  transition: opacity 0.4s ease, filter 0.4s ease;
}

/* ── 边: Diff Mode 样式 ── */

/* added 边: 绿色 */
.code-graph-flow :deep(.vue-flow__edge.diff-edge-added .vue-flow__edge-path) {
  stroke: #22c55e !important;
  stroke-width: 2.5px !important;
  filter: drop-shadow(0 0 6px rgba(34, 197, 94, 0.5));
}

/* modified 边: 黄色 */
.code-graph-flow :deep(.vue-flow__edge.diff-edge-modified .vue-flow__edge-path) {
  stroke: #facc15 !important;
  stroke-width: 2.5px !important;
  filter: drop-shadow(0 0 6px rgba(250, 204, 21, 0.5));
}

/* impacted 边: 橙色虚线 */
.code-graph-flow :deep(.vue-flow__edge.diff-edge-impacted .vue-flow__edge-path) {
  stroke: #f97316 !important;
  stroke-width: 2px !important;
  stroke-dasharray: 6 3 !important;
  filter: drop-shadow(0 0 4px rgba(249, 115, 22, 0.4));
}

/* deleted 边: 红色虚线 */
.code-graph-flow :deep(.vue-flow__edge.diff-edge-deleted .vue-flow__edge-path) {
  stroke: #ef4444 !important;
  stroke-width: 1.5px !important;
  stroke-dasharray: 4 4 !important;
  opacity: 0.5;
}

/* unchanged 边: 灰化 */
.code-graph-flow :deep(.vue-flow__edge.diff-edge-unchanged .vue-flow__edge-path) {
  stroke: #334155 !important;
  stroke-width: 1px !important;
  opacity: 0.15;
}

.node-highlighted {
  animation: node-glow-pulse 1.5s ease-in-out infinite;
}

@keyframes node-glow-pulse {
  0%, 100% { filter: brightness(1); }
  50% { filter: brightness(1.3); }
}

.node-icon {
  font-size: 11px;
  flex-shrink: 0;
}

.node-label {
  font-size: 11px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.node-badge {
  font-size: 8px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.graph-slide-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.graph-slide-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}
.graph-slide-enter-from {
  opacity: 0;
}
.graph-slide-enter-from > :nth-child(2) {
  transform: translateX(100%);
}
.graph-slide-leave-to {
  opacity: 0;
}
.graph-slide-leave-to > :nth-child(2) {
  transform: translateX(100%);
}
.graph-slide-enter-active > :nth-child(2) {
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.graph-slide-leave-active > :nth-child(2) {
  transition: transform 0.25s cubic-bezier(0.4, 0, 1, 1);
}
</style>
