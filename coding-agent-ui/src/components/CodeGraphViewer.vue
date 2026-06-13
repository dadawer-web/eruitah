<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { VueFlow, useVueFlow, Position, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { toPng } from 'html-to-image'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { getLayoutedElements } from '../utils/elkLayout.js'
import { useAgentStore } from '../stores/agent.js'

const store = useAgentStore()

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
const learnNode = ref(null)
const searchQuery = ref('')
const searchInputRef = ref(null)
const hasData = ref(false)

// ── 语义向量检索状态 ──
const semanticMatches = ref([])  // 后端返回的语义匹配节点 ID
const isSearching = ref(false)
let searchTimeout = null

// ── Persona 角色自适应 UI ──
const currentPersona = ref('dev')  // 'manager' | 'dev' | 'geek'
const collapsedGroups = ref(new Set())

// ── 布局模式切换 ──
const layoutMode = ref('structural')  // 'structural' | 'flow'

// ── 层级过滤器 (Layer Filter) ──
const availableLayers = ref([])
const visibleLayers = ref([])
const showFilterPanel = ref(false)

// ── Path Finder 状态 ──
const selectedPathNodes = ref([])   // 最多 2 个 nodeId：[起点, 终点]
const highlightedPath = ref({ nodeIds: new Set(), edgeIds: new Set() })

// ── Diff Mode 状态 ──
const isDiffMode = ref(false)

// ── Persona 自动折叠逻辑 ──
watch(currentPersona, (newRole) => {
  const allGroupIds = []
  const rawNodes = props.graphData?.nodes || []
  const groupSet = new Set()
  rawNodes.forEach(n => {
    const cid = n.cluster_id || (n.data && n.data.cluster_id)
    if (cid) groupSet.add(String(cid))
  })
  groupSet.forEach(id => allGroupIds.push(id))

  if (newRole === 'manager') {
    collapsedGroups.value = new Set(allGroupIds)
  } else {
    collapsedGroups.value = new Set()
  }
  processGraph()
})

// ── 漫游导览状态机 ──
const { setCenter, fitView } = useVueFlow()
const isTouring = ref(false)
const currentTourIndex = ref(0)
const tourSteps = ref([])

function startTour() {
  const allCodeNodes = flowNodes.value.filter(n => n.type !== 'group')
  if (allCodeNodes.length === 0) return
  tourSteps.value = allCodeNodes.slice(0, Math.min(10, allCodeNodes.length))
  currentTourIndex.value = 0
  isTouring.value = true
  executeCameraMove()
}

function stopTour() {
  isTouring.value = false
  currentTourIndex.value = 0
  setTimeout(() => fitView({ duration: 800, padding: 0.2 }), 100)
}

function prevStep() {
  if (currentTourIndex.value > 0) {
    currentTourIndex.value--
    executeCameraMove()
  }
}

function nextStep() {
  if (currentTourIndex.value < tourSteps.value.length - 1) {
    currentTourIndex.value++
    executeCameraMove()
  }
}

function executeCameraMove() {
  const targetId = tourSteps.value[currentTourIndex.value]?.id
  const targetNode = flowNodes.value.find(n => n.id === targetId)
  if (targetNode) {
    const width = parseFloat(targetNode.style?.width) || 240
    const height = parseFloat(targetNode.style?.height) || 60
    setCenter({
      x: targetNode.position.x + width / 2,
      y: targetNode.position.y + height / 2,
      zoom: 1.6,
      duration: 1200
    })
  }
}

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

// 领域聚合配色方案
const DOMAIN_COLORS = [
  { border: '#3b82f6', bg: 'rgba(59,130,246,0.06)', text: '#60a5fa' },   // 蓝
  { border: '#a855f7', bg: 'rgba(168,85,247,0.06)', text: '#c084fc' },   // 紫
  { border: '#f59e0b', bg: 'rgba(245,158,11,0.06)', text: '#fbbf24' },   // 琥珀
  { border: '#10b981', bg: 'rgba(16,185,129,0.06)', text: '#34d399' },   // 翠绿
  { border: '#ef4444', bg: 'rgba(239,68,68,0.06)', text: '#f87171' },    // 红
  { border: '#ec4899', bg: 'rgba(236,72,153,0.06)', text: '#f472b6' },   // 粉
  { border: '#06b6d4', bg: 'rgba(6,182,212,0.06)', text: '#22d3ee' },    // 青
  { border: '#8b5cf6', bg: 'rgba(139,92,246,0.06)', text: '#a78bfa' },   // 靛
]

function mapBackendToVueFlow(backendData) {
  if (!backendData?.nodes?.length) return { nodes: [], edges: [] }

  // 1. 收集所有 cluster_id → 创建 Domain Group 结界节点
  const clusterMap = new Map()  // cluster_id → { name, colorIdx, nodes[] }
  for (const n of backendData.nodes) {
    const cid = n.cluster_id || n.data?.cluster_id
    if (!cid) continue
    if (!clusterMap.has(cid)) {
      const cname = n.cluster_name || n.data?.cluster_name || cid
      clusterMap.set(cid, { name: cname, colorIdx: clusterMap.size % DOMAIN_COLORS.length, nodes: [] })
    }
    clusterMap.get(cid).nodes.push(n)
  }

  const groupNodes = []
  for (const [cid, info] of clusterMap) {
    const dc = DOMAIN_COLORS[info.colorIdx]
    groupNodes.push({
      id: cid,
      type: 'group',
      position: { x: 0, y: 0 },
      style: {
        backgroundColor: dc.bg,
        border: `2px dashed ${dc.border}80`,
        borderRadius: '16px',
        zIndex: -1,
        width: '400px',
        height: '300px',
      },
      data: {
        label: info.name,
        nodeType: 'domain-group',
        color: dc.text,
        border: dc.border,
        bg: dc.bg,
        icon: '📦',
        isDomainGroup: true,
      },
    })
  }

  // 2. 映射业务节点
  const vfNodes = backendData.nodes.map((n) => {
    const layer = n.layer || 'unknown'
    const layerStyle = resolveLayerStyle(layer)
    const nodeType = n.type || 'Function'
    const cid = n.cluster_id || n.data?.cluster_id
    const cname = n.cluster_name || n.data?.cluster_name
    const domainColor = cid ? DOMAIN_COLORS[clusterMap.get(cid)?.colorIdx ?? 0] : null

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
        clusterId: cid || null,
        clusterName: cname || null,
        domainColor: domainColor ? domainColor.text : null,
        domainBorder: domainColor ? domainColor.border : null,
        extra: n,
      },
      style: {
        width: (nodeType === 'File' ? 260 : nodeType === 'Class' ? 200 : 180) + 'px',
        height: (nodeType === 'File' ? 56 : nodeType === 'Class' ? 44 : 40) + 'px',
        // 如果属于某个 domain，给节点加微妙的领域色边框
        ...(domainColor ? { borderLeft: `3px solid ${domainColor.border}` } : {}),
      },
      sourcePosition: Position.RIGHT,
      targetPosition: Position.LEFT,
      // 标记归属 domain（用于 ELK 布局分组）
      _domainGroup: cid || null,
    }
  })

  // 3. 合并 group 节点 + 业务节点
  const allNodes = [...groupNodes, ...vfNodes]

  // 4. 映射边
  const validIds = new Set(allNodes.map((n) => n.id))
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

  return { nodes: allNodes, edges: vfEdges }
}

async function processGraph() {
  if (!props.graphData?.nodes?.length) return

  layoutLoading.value = true
  error.value = null

  try {
    const { nodes: rawNodes, edges: rawEdges } = mapBackendToVueFlow(props.graphData)
    const collapsed = collapsedGroups.value
    const layers = visibleLayers.value

    // ── 层级检测 ──
    const layerSet = new Set()
    for (const n of rawNodes) {
      const layer = n.data?.layer || 'unknown'
      if (layer !== 'unknown') layerSet.add(layer)
    }
    const detectedLayers = [...layerSet].sort()
    if (availableLayers.value.length === 0 || availableLayers.value.join(',') !== detectedLayers.join(',')) {
      availableLayers.value = detectedLayers
      if (visibleLayers.value.length === 0) visibleLayers.value = [...detectedLayers]
    }

    // ── 层级过滤 ──
    let filteredNodes = rawNodes
    if (layers.length > 0) {
      filteredNodes = rawNodes.filter(n => {
        if (n.type === 'group') return true
        const layer = n.data?.layer || 'unknown'
        return layers.includes(layer)
      })
    }

    // ── 容器折叠：隐藏折叠组内的子节点 ──
    const collapsedSet = collapsed
    const groupNodeIds = new Set(filteredNodes.filter(n => n.type === 'group').map(n => n.id))
    const visibleNodes = filteredNodes.filter(n => {
      if (n.type === 'group') return true
      const domainGroup = n._domainGroup
      if (domainGroup && collapsedSet.has(domainGroup)) return false
      return true
    })

    // 更新折叠的 group 节点样式
    const finalNodes = visibleNodes.map(n => {
      if (n.type === 'group' && n.data?.isDomainGroup) {
        const isCollapsed = collapsedSet.has(n.id)
        return {
          ...n,
          style: {
            ...n.style,
            backgroundColor: isCollapsed ? 'rgba(30, 58, 138, 0.12)' : n.style.backgroundColor,
            border: isCollapsed ? '2px solid rgba(59, 130, 246, 0.8)' : n.style.border,
            ...(isCollapsed ? { width: '280px', height: '80px' } : {}),
          },
          data: {
            ...n.data,
            isCollapsed,
            label: isCollapsed ? `${n.data.label} (➕)` : `${n.data.label} (➖)`,
          },
        }
      }
      return n
    })

    // ── 边聚合：折叠时重定向边到父组 ──
    const visibleIds = new Set(finalNodes.map(n => n.id))
    // 从所有原始节点（含被过滤的子节点）构建 nodeToGroup 映射
    const nodeToGroup = new Map()
    for (const n of filteredNodes) {
      if (n.type !== 'group' && n._domainGroup) {
        nodeToGroup.set(n.id, n._domainGroup)
      }
    }

    const edgeAggregationMap = new Map()
    for (const edge of rawEdges) {
      let sourceId = edge.source
      let targetId = edge.target

      if (!visibleIds.has(sourceId)) {
        const group = nodeToGroup.get(sourceId)
        if (group && collapsedSet.has(group)) {
          sourceId = group
        } else {
          continue
        }
      }

      if (!visibleIds.has(targetId)) {
        const group = nodeToGroup.get(targetId)
        if (group && collapsedSet.has(group)) {
          targetId = group
        } else {
          continue
        }
      }

      if (sourceId === targetId) continue

      const edgeKey = `${sourceId}→${targetId}`
      if (edgeAggregationMap.has(edgeKey)) {
        const existing = edgeAggregationMap.get(edgeKey)
        existing.count++
      } else {
        edgeAggregationMap.set(edgeKey, {
          source: sourceId,
          target: targetId,
          count: 1,
          edge,
        })
      }
    }

    const finalEdges = []
    let edgeIdx = 0
    const isFlowMode = layoutMode.value === 'flow'
    for (const [, agg] of edgeAggregationMap) {
      const e = agg.edge
      const isAggregated = agg.count > 1
      finalEdges.push({
        ...e,
        id: `e-${agg.source}-${agg.target}-${edgeIdx++}`,
        source: agg.source,
        target: agg.target,
        type: isFlowMode ? 'step' : (e.type || 'smoothstep'),
        style: {
          ...e.style,
          ...(isAggregated ? { strokeWidth: Math.min(2 + agg.count * 0.5, 5) } : {}),
          ...(isFlowMode ? { strokeWidth: Math.max(e.style?.strokeWidth || 2, 3) } : {}),
        },
        label: isAggregated ? `${e.label || 'ref'} ×${agg.count}` : e.label,
      })
    }

    const { nodes: layouted, edges } = await getLayoutedElements(finalNodes, finalEdges, { mode: layoutMode.value })

    flowNodes.value = []
    flowEdges.value = []
    await nextTick()

    flowNodes.value = layouted
    flowEdges.value = edges
    hasData.value = true

    // 布局完成后自动适配视图
    await nextTick()
    setTimeout(() => fitView({ duration: 400, padding: 0.15 }), 50)
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
  if (!searchQuery.value && !isTouring.value && semanticMatches.value.length === 0) return flowNodes.value
  const q = searchQuery.value.toLowerCase()

  // 漫游模式：高亮当前节点 + 相邻节点，暗化其余
  if (isTouring.value && tourSteps.value.length > 0) {
    const activeNodeId = tourSteps.value[currentTourIndex.value]?.id
    const neighborIds = new Set()
    for (const e of flowEdges.value) {
      if (e.source === activeNodeId) neighborIds.add(e.target)
      if (e.target === activeNodeId) neighborIds.add(e.source)
    }

    return flowNodes.value.map(n => {
      let style = { ...n.style }
      if (n.id === activeNodeId) {
        style.opacity = 1
        style.boxShadow = '0 0 30px rgba(59,130,246,0.9)'
        style.zIndex = 100
      } else if (neighborIds.has(n.id)) {
        style.opacity = 1
        style.boxShadow = '0 0 12px rgba(59,130,246,0.3)'
      } else {
        style.opacity = 0.08
      }
      return { ...n, style }
    })
  }

  // 语义搜索模式：后端返回的匹配节点发蓝光
  const semanticIds = new Set(semanticMatches.value)
  const hasSemanticResults = semanticIds.size > 0

  // 关键词匹配
  const keywordMatchedIds = new Set()
  if (q) {
    for (const n of flowNodes.value) {
      const label = (n.data?.label || '').toLowerCase()
      const nodeType = (n.data?.nodeType || '').toLowerCase()
      if (label.includes(q) || nodeType.includes(q)) {
        keywordMatchedIds.add(n.id)
      }
    }
  }

  // 合并匹配：语义匹配 + 关键词匹配
  const allMatchedIds = new Set([...semanticIds, ...keywordMatchedIds])

  // 找出匹配节点的所属 group
  const groupIdsToShow = new Set()
  for (const n of flowNodes.value) {
    if (allMatchedIds.has(n.id) && n._domainGroup) {
      groupIdsToShow.add(n._domainGroup)
    }
  }

  // 没有任何匹配时，返回原始节点
  if (allMatchedIds.size === 0 && !q) return flowNodes.value

  return flowNodes.value.map(n => {
    const isSemanticMatch = semanticIds.has(n.id)
    const isKeywordMatch = keywordMatchedIds.has(n.id)
    const isMatch = isSemanticMatch || isKeywordMatch
    const isGroupToShow = n.type === 'group' && groupIdsToShow.has(n.id)
    let style = { ...n.style }
    if (isMatch || isGroupToShow || n.type === 'group') {
      style.opacity = isMatch ? 1 : 0.6
      if (isSemanticMatch) {
        // 语义匹配：蓝光
        style.boxShadow = '0 0 25px rgba(59,130,246,0.8)'
        style.borderColor = '#3b82f6'
      } else if (isKeywordMatch) {
        // 关键词匹配：琥珀光
        style.boxShadow = '0 0 20px rgba(245, 158, 11, 0.6)'
      }
    } else {
      style.opacity = 0.08
    }
    return { ...n, style }
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
  const semanticIds = new Set(semanticMatches.value)
  const hasSemantic = semanticIds.size > 0

  // 漫游模式：高亮当前节点相连的边
  if (isTouring.value && tourSteps.value.length > 0) {
    const activeNodeId = tourSteps.value[currentTourIndex.value]?.id
    return flowEdges.value.map(e => {
      if (e.source === activeNodeId || e.target === activeNodeId) {
        return {
          ...e,
          style: { ...e.style, stroke: '#3b82f6', opacity: 1, strokeWidth: 3 },
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed, color: '#3b82f6', width: 12, height: 12 },
        }
      }
      return { ...e, style: { ...e.style, opacity: 0.05 } }
    })
  }

  return flowEdges.value
    .filter((e) => ids.has(e.source) && ids.has(e.target))
    .map((e) => {
      const isOnPath = pathActive && pathEdgeIds.has(e.id)
      const ds = e.diffStatus

      // 语义搜索：匹配节点相连的边发红光
      const isSemanticEdge = hasSemantic && (semanticIds.has(e.source) || semanticIds.has(e.target))

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

      // 语义搜索边高亮
      if (isSemanticEdge) {
        return {
          ...e,
          animated: true,
          style: { stroke: '#ef4444', strokeWidth: 2, opacity: 1 },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444', width: 12, height: 12 },
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
    // 普通点击：走原有逻辑 + 打开 Learn Panel
    selectedNode.value = event.node?.data?.extra || null
    learnNode.value = event.node || null
    emit('nodeClick', event.node?.data?.extra)
    return
  }

  // Shift + Click: Path Finder 逻辑
  if (selectedPathNodes.value.length >= 2) {
    selectedPathNodes.value = [nodeId]
    highlightedPath.value = { nodeIds: new Set(), edgeIds: new Set() }
    return
  }

  selectedPathNodes.value.push(nodeId)

  if (selectedPathNodes.value.length === 2) {
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

// ── 双击折叠/展开结界 ──
let _lastToggleTime = 0
function onNodeDoubleClick(event) {
  // 防抖：300ms 内只允许一次切换（防止 VueFlow 事件 + 自定义模板事件双重触发）
  const now = Date.now()
  if (now - _lastToggleTime < 300) return
  _lastToggleTime = now

  const node = event.node
  if (!node?.data?.isDomainGroup) return
  const gid = node.id
  const newCollapsed = new Set(collapsedGroups.value)
  if (newCollapsed.has(gid)) {
    newCollapsed.delete(gid)
  } else {
    newCollapsed.add(gid)
  }
  collapsedGroups.value = newCollapsed

  // 用 nextTick 确保 collapsedGroups 响应式更新后再布局
  nextTick(() => processGraph())
}

function handlePaneClick() {
  selectedNode.value = null
  learnNode.value = null
  clearPathFinder()
}

// AI 分析：重试/手动触发
function retryAnalysis() {
  if (learnNode.value?.id) {
    // 清除旧结果，强制重新分析
    delete store.nodeAnalysisMap[learnNode.value.id]
    store.analyzeNode(learnNode.value)
  }
}

// 渲染 AI 分析结果（Markdown 粗体/列表 → HTML）
function renderAnalysis(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong class="text-blue-300">$1</strong>')
    .replace(/^(\d+)\.\s/gm, '<span class="text-purple-400 font-bold">$1.</span> ')
    .replace(/^- /gm, '<span class="text-purple-400">•</span> ')
    .replace(/\n/g, '<br>')
}

const isNodeActive = (nodeId) => {
  if (!props.activeNodeId) return true
  return nodeId === props.activeNodeId
}

const isNodeHighlighted = (nodeId) => {
  return props.activeNodeId && nodeId === props.activeNodeId
}

// ── 全局快捷键引擎 ──
function handleGlobalKeydown(e) {
  const isInputFocused = document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA'

  // / 键：聚焦搜索框
  if (e.key === '/' && !isInputFocused) {
    e.preventDefault()
    searchInputRef.value?.focus()
    return
  }

  // Esc 键：关闭面板 > 清空搜索 > 退出漫游 > 关闭 viewer
  if (e.key === 'Escape') {
    if (learnNode.value) {
      learnNode.value = null
      selectedNode.value = null
    } else if (searchQuery.value) {
      searchQuery.value = ''
      searchInputRef.value?.blur()
    } else if (isTouring.value) {
      stopTour()
    } else if (!selectedNode.value) {
      emit('close')
    }
    return
  }

  // ← → 键：漫游控制
  if (isTouring.value && !isInputFocused) {
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      prevStep()
      return
    }
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      nextStep()
      return
    }
  }

  // d 键：切换 Diff Mode
  if (e.key === 'd' && !isInputFocused) {
    isDiffMode.value = !isDiffMode.value
    return
  }
}

// ── 语义向量检索：防抖 watch ──
watch(searchQuery, (newVal) => {
  // 清除旧定时器
  if (searchTimeout) {
    clearTimeout(searchTimeout)
    searchTimeout = null
  }

  // 空查询时清空语义匹配
  if (!newVal || !newVal.trim()) {
    semanticMatches.value = []
    isSearching.value = false
    return
  }

  // 500ms 防抖后调用语义搜索 API
  isSearching.value = true
  searchTimeout = setTimeout(async () => {
    try {
      const resp = await fetch(`/api/v1/semantic_search?q=${encodeURIComponent(newVal.trim())}&top_k=10`)
      if (resp.ok) {
        const data = await resp.json()
        if (data.status === 'success' && data.matches) {
          semanticMatches.value = data.matches
        }
      }
    } catch (e) {
      // 语义搜索失败时静默降级，仅使用关键词匹配
      semanticMatches.value = []
    } finally {
      isSearching.value = false
    }
  }, 500)
})

// ── 一键高清导出图谱 ──
const isExporting = ref(false)
const downloadImage = async () => {
  const flowElement = document.querySelector('.vue-flow__viewport')
  if (!flowElement) return

  isExporting.value = true
  try {
    // 截图前居中视图，保证完整性
    fitView({ padding: 0.1, duration: 0 })
    await new Promise(resolve => setTimeout(resolve, 300))

    const dataUrl = await toPng(flowElement, {
      backgroundColor: '#0a0a0a',
      pixelRatio: 2,
      filter: (node) => {
        // 过滤掉 Vue Flow 自带的面板控件
        if (node?.classList?.contains('vue-flow__panel')) return false
        return true
      }
    })

    const link = document.createElement('a')
    link.download = `architecture-graph-${new Date().getTime()}.png`
    link.href = dataUrl
    link.click()
  } catch (error) {
    console.error('导出图片失败:', error)
  } finally {
    isExporting.value = false
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleGlobalKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
})

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
                ref="searchInputRef"
                v-model="searchQuery"
                placeholder="搜索节点 (支持语义)..."
                class="w-44 px-2.5 py-1 text-[11px] bg-slate-900/80 border border-slate-700/60 rounded-md text-slate-300 placeholder-slate-600 focus:outline-none focus:border-emerald-500/50 transition-colors"
              />
              <span v-if="isSearching" class="absolute right-2 top-1/2 -translate-y-1/2 animate-spin text-blue-400 text-[10px]">⟳</span>
              <span v-else-if="semanticMatches.length > 0" class="absolute right-2 top-1/2 -translate-y-1/2 text-blue-400 text-[10px]">✦</span>
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

          <!-- 右上角全息控制面板 -->
          <div class="absolute right-4 top-4 z-50 flex flex-col gap-2 items-end">
            <!-- Persona 切换器 -->
            <div class="persona-switcher">
              <button
                @click="currentPersona = 'manager'"
                :class="currentPersona === 'manager' ? 'persona-btn-active' : 'persona-btn'"
                title="架构师视角：全部折叠，只看模块大框"
              >👔 宏观</button>
              <button
                @click="currentPersona = 'dev'"
                :class="currentPersona === 'dev' ? 'persona-btn-active' : 'persona-btn'"
                title="开发视角：标准展开"
              >💻 业务</button>
              <button
                @click="currentPersona = 'geek'"
                :class="currentPersona === 'geek' ? 'persona-btn-active' : 'persona-btn'"
                title="极客视角：全部展开，细致入微"
              >🔬 微观</button>
            </div>

            <!-- 过滤面板切换按钮 -->
            <button @click="showFilterPanel = !showFilterPanel" class="filter-toggle-btn">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              <span class="text-[10px]">LAYER</span>
              <span v-if="visibleLayers.length < availableLayers.length" class="filter-count-badge">{{ visibleLayers.length }}/{{ availableLayers.length }}</span>
            </button>

            <!-- 层级过滤面板 -->
            <Transition name="filter-slide">
              <div v-if="showFilterPanel" class="filter-panel">
                <div class="filter-panel-header">
                  <span class="text-[10px] font-bold text-gray-400 tracking-wider">LAYER FILTER</span>
                  <div class="flex gap-2">
                    <button @click="visibleLayers = [...availableLayers]; processGraph()" class="filter-action-btn">全选</button>
                    <button @click="visibleLayers = []; processGraph()" class="filter-action-btn">清空</button>
                  </div>
                </div>
                <div class="filter-panel-body">
                  <label
                    v-for="layer in availableLayers"
                    :key="layer"
                    class="filter-checkbox-row"
                  >
                    <input
                      type="checkbox"
                      :value="layer"
                      v-model="visibleLayers"
                      @change="processGraph()"
                      class="filter-checkbox"
                    />
                    <span class="filter-layer-dot" :style="{ background: getLayerStyle(layer).miniMap }"></span>
                    <span class="filter-layer-label" :style="{ color: getLayerStyle(layer).text }">
                      {{ getLayerStyle(layer).label }}
                    </span>
                    <span class="filter-layer-count">
                      {{ props.graphData?.nodes?.filter(n => (n.layer || n.data?.layer || 'unknown') === layer).length || 0 }}
                    </span>
                  </label>
                </div>
              </div>
            </Transition>

            <!-- 解析项目架构按钮 -->
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

            <!-- Diff 时光机控制区 -->
            <button
              @click="isDiffMode = !isDiffMode"
              :class="isDiffMode
                ? 'bg-orange-600/90 border-orange-500 shadow-[0_0_12px_rgba(234,88,12,0.7)] text-white'
                : 'bg-gray-900/80 border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-500'"
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[10px] font-bold font-mono tracking-wider transition-all duration-300 cursor-pointer hover:scale-105"
            >
              <span>{{ isDiffMode ? '🔥' : '⏳' }}</span>
              <span>{{ isDiffMode ? 'DIFF: ON' : '时光机' }}</span>
            </button>

            <!-- Diff 图例 -->
            <Transition name="filter-slide">
              <div v-if="isDiffMode" class="mt-2 flex flex-col gap-1.5 text-[10px] font-mono bg-black/50 p-2.5 rounded border border-gray-800">
                <div class="flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]"></span> 新增 (Added)</div>
                <div class="flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full bg-amber-500 shadow-[0_0_8px_#f59e0b]"></span> 修改 (Modified)</div>
                <div class="flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_8px_#ef4444] border border-dashed"></span> 移除 (Removed)</div>
              </div>
            </Transition>

            <!-- 布局模式切换 -->
            <div class="flex bg-gray-900/50 rounded-lg p-1 border border-gray-700/50 mt-2">
              <button
                @click="layoutMode = 'structural'; processGraph()"
                :class="layoutMode === 'structural' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-400 hover:text-gray-200'"
                class="flex-1 py-1.5 text-[10px] font-bold rounded transition-all font-mono"
              >🕸️ 结构拓扑</button>
              <button
                @click="layoutMode = 'flow'; processGraph()"
                :class="layoutMode === 'flow' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-400 hover:text-gray-200'"
                class="flex-1 py-1.5 text-[10px] font-bold rounded transition-all font-mono"
              >➡️ 业务流程</button>
            </div>

            <!-- 一键高清导出 -->
            <button
              @click="downloadImage"
              :disabled="isExporting"
              class="mt-2 w-full flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:from-gray-700 disabled:to-gray-700 disabled:cursor-wait text-white text-xs font-bold rounded-lg shadow-[0_0_15px_rgba(79,70,229,0.5)] transition-all transform hover:scale-105 active:scale-95"
            >
              <svg v-if="!isExporting" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
              <span v-else class="animate-spin text-[10px]">⟳</span>
              <span>{{ isExporting ? '导出中...' : '一键导出高清图' }}</span>
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
            @node-double-click="onNodeDoubleClick"
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

            <!-- Domain Group 结界节点 -->
            <template #node-group="groupNodeProps">
              <div v-if="groupNodeProps.data?.isDomainGroup" class="code-domain-group-node" :class="{ 'code-domain-collapsed': groupNodeProps.data?.isCollapsed }" @dblclick.stop="onNodeDoubleClick({ node: groupNodeProps })">
                <div class="code-domain-group-label" :class="{ 'code-domain-label-collapsed': groupNodeProps.data?.isCollapsed }" :style="{ borderColor: groupNodeProps.data?.border + '60' }">
                  <span class="text-[10px] mr-1">{{ groupNodeProps.data?.isCollapsed ? '➕' : '➖' }}</span>
                  <span class="text-[10px] font-bold" :style="{ color: groupNodeProps.data?.color }">{{ groupNodeProps.data?.label }}</span>
                </div>
                <div v-if="groupNodeProps.data?.isCollapsed" class="code-domain-collapsed-hint">双击展开</div>
              </div>
            </template>
          </VueFlow>

          <!-- AI 沉浸式漫游导览控制器 -->
          <div v-if="flowNodes.length && !isTouring" class="absolute bottom-10 left-1/2 -translate-x-1/2 z-[9999]">
            <button
              @click="startTour"
              class="px-8 py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-full shadow-[0_0_20px_rgba(59,130,246,0.6)] transition-all transform hover:scale-105"
            >
              ▶ 启动全息漫游
            </button>
          </div>

          <div v-if="isTouring && tourSteps.length > 0" class="absolute bottom-10 left-1/2 -translate-x-1/2 z-[9999]">
            <div class="flex items-center gap-6 px-6 py-4 bg-gray-900/90 backdrop-blur-xl border border-gray-700 rounded-2xl shadow-2xl">
              <div class="flex flex-col">
                <span class="text-xs text-gray-400 font-mono">STEP {{ currentTourIndex + 1 }} / {{ tourSteps.length }}</span>
                <span class="text-sm text-blue-400 font-bold max-w-[200px] truncate">
                  {{ tourSteps[currentTourIndex]?.data?.label || 'Unknown Node' }}
                </span>
              </div>

              <div class="flex items-center gap-2 border-l border-gray-700 pl-6">
                <button @click="prevStep" :disabled="currentTourIndex === 0" class="p-2 hover:bg-gray-800 rounded disabled:opacity-30 text-white">⏪</button>
                <button @click="stopTour" class="px-4 py-2 bg-red-500/20 hover:bg-red-500/40 text-red-400 rounded text-sm font-bold transition-colors">⏹ 退出</button>
                <button @click="nextStep" :disabled="currentTourIndex === tourSteps.length - 1" class="p-2 hover:bg-gray-800 rounded disabled:opacity-30 text-white">⏩</button>
              </div>
            </div>
          </div>

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
            <div class="flex items-center gap-2 text-[9px] bg-black/70 backdrop-blur-sm border border-slate-700/40 rounded-md px-2.5 py-1.5 pointer-events-auto">
              <kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">/</kbd><span class="text-slate-400">搜索</span>
              <kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">Esc</kbd><span class="text-slate-400">关闭</span>
              <kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">d</kbd><span class="text-slate-400">Diff</span>
              <kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">←→</kbd><span class="text-slate-400">漫游</span>
            </div>
            <div class="flex items-center gap-2 text-[9px] bg-black/70 backdrop-blur-sm border border-slate-700/40 rounded-md px-2.5 py-1.5 pointer-events-auto">
              <span class="text-slate-400">双击结界</span><span class="text-blue-400">折叠/展开</span>
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

        <!-- 右侧全息属性抽屉 (Learn Panel) — 最外层容器，z-[10000] -->
        <transition name="slide-right">
          <div v-if="learnNode" class="absolute top-0 right-0 h-full w-96 bg-gray-900/95 backdrop-blur-2xl border-l border-gray-700 shadow-2xl z-[10000] flex flex-col" style="pointer-events: auto;">

            <div class="p-6 border-b border-gray-700/50 flex justify-between items-start">
              <div>
                <div class="text-xs text-blue-400 font-mono mb-1">NODE INSPECTOR</div>
                <h2 class="text-xl font-bold text-white break-all">{{ learnNode.data?.label || learnNode.id }}</h2>
              </div>
              <button @click="learnNode = null" class="text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-full w-8 h-8 flex items-center justify-center transition-colors shrink-0 ml-2">✕</button>
            </div>

            <div class="p-6 overflow-y-auto flex-1 space-y-8 custom-scrollbar">

              <div>
                <h3 class="text-xs text-gray-500 font-bold uppercase tracking-wider mb-2">System Domain</h3>
                <div class="flex flex-wrap gap-1.5">
                  <span v-if="learnNode.data?.clusterName" class="inline-flex items-center gap-1 px-3 py-1 rounded text-sm border" :style="{ color: learnNode.data?.domainColor || '#60a5fa', background: (learnNode.data?.domainBorder || '#3b82f6') + '12', borderColor: (learnNode.data?.domainBorder || '#3b82f6') + '40' }">
                    <span class="text-[10px]">📦</span>{{ learnNode.data.clusterName }}
                  </span>
                  <span class="inline-block px-3 py-1 bg-blue-900/30 text-blue-300 rounded text-sm border border-blue-800/50">
                    {{ learnNode.data?.layerLabel || learnNode.data?.layer || 'Unknown Layer' }}
                  </span>
                </div>
              </div>

              <div>
                <h3 class="text-xs text-gray-500 font-bold uppercase tracking-wider mb-2">Node Type</h3>
                <span class="inline-block px-3 py-1 bg-purple-900/30 text-purple-300 rounded text-sm border border-purple-800/50">
                  {{ learnNode.data?.nodeType || learnNode.data?.badge || 'Unknown' }}
                </span>
              </div>

              <div v-if="learnNode.data?.filePath">
                <h3 class="text-xs text-gray-500 font-bold uppercase tracking-wider mb-2">File Path</h3>
                <div class="text-sm text-gray-400 font-mono bg-gray-800/40 p-2.5 rounded-lg border border-gray-700/50 break-all">{{ learnNode.data.filePath }}</div>
              </div>

              <div>
                <h3 class="text-xs text-gray-500 font-bold uppercase tracking-wider mb-3">AST Symbols (Functions)</h3>
                <div v-if="(learnNode.data?.extra?.methods?.length || learnNode.data?.extra?.symbols?.length)" class="space-y-2">
                  <div v-for="(sym, idx) in (learnNode.data?.extra?.symbols || learnNode.data?.extra?.methods || [])" :key="idx" class="flex items-center gap-3 text-sm text-gray-300 bg-gray-800/40 p-2.5 rounded-lg border border-gray-700/50 hover:bg-gray-700 transition-colors">
                    <span class="text-purple-400 font-mono bg-purple-900/30 px-1.5 rounded">ƒ</span>
                    <span class="truncate font-mono text-xs">{{ typeof sym === 'string' ? sym : sym.name || sym }}</span>
                  </div>
                </div>
                <div v-else class="text-sm text-gray-500 italic bg-gray-800/20 p-4 rounded-lg border border-gray-800 border-dashed text-center">
                  No internal symbols extracted.
                </div>
              </div>

              <div v-if="learnNode.data?.extra?.params?.length || learnNode.data?.extra?.return_type">
                <h3 class="text-xs text-gray-500 font-bold uppercase tracking-wider mb-3">Signature</h3>
                <div class="space-y-2">
                  <div v-if="learnNode.data?.extra?.params?.length" class="text-sm text-gray-400 bg-gray-800/40 p-2.5 rounded-lg border border-gray-700/50">
                    <span class="text-gray-500 text-xs">params:</span> <span class="font-mono text-xs">{{ learnNode.data.extra.params.join(', ') }}</span>
                  </div>
                  <div v-if="learnNode.data?.extra?.return_type" class="text-sm text-gray-400 bg-gray-800/40 p-2.5 rounded-lg border border-gray-700/50">
                    <span class="text-gray-500 text-xs">returns:</span> <span class="font-mono text-xs">{{ learnNode.data.extra.return_type }}</span>
                  </div>
                </div>
              </div>

              <div>
                <h3 class="text-xs text-gray-500 font-bold uppercase tracking-wider mb-3">AI Architecture Analysis</h3>

                <!-- 加载中 -->
                <div v-if="store.nodeAnalysisMap[learnNode.id]?.loading" class="text-sm text-gray-400 leading-relaxed bg-blue-900/10 p-4 rounded-lg border border-blue-900/30 relative overflow-hidden">
                  <div class="absolute inset-0 bg-gradient-to-r from-transparent via-blue-900/10 to-transparent animate-[shimmer_2s_infinite]"></div>
                  <div class="flex items-center gap-2">
                    <span class="inline-block w-3 h-3 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin"></span>
                    <span class="animate-pulse text-blue-300">AI 正在深度分析该模块...</span>
                  </div>
                </div>

                <!-- 分析结果 -->
                <div v-else-if="store.nodeAnalysisMap[learnNode.id]?.analysis" class="text-sm text-gray-300 leading-relaxed bg-gradient-to-br from-blue-900/10 to-purple-900/10 p-4 rounded-lg border border-blue-900/30">
                  <div class="whitespace-pre-wrap" v-html="renderAnalysis(store.nodeAnalysisMap[learnNode.id].analysis)"></div>
                </div>

                <!-- 分析失败 -->
                <div v-else-if="store.nodeAnalysisMap[learnNode.id]?.error" class="text-sm text-red-400 bg-red-900/10 p-4 rounded-lg border border-red-900/30">
                  分析失败，<button @click="retryAnalysis" class="text-blue-400 underline hover:text-blue-300">点击重试</button>
                </div>

                <!-- 未分析：手动触发 -->
                <div v-else class="text-sm text-gray-400 bg-gray-800/20 p-4 rounded-lg border border-gray-800 border-dashed text-center">
                  <button @click="retryAnalysis" class="text-blue-400 hover:text-blue-300 transition-colors">
                    <span class="mr-1">🧠</span>点击启动 AI 架构分析
                  </button>
                </div>
              </div>

            </div>
          </div>
        </transition>
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

/* ══════════════════════════════════════════════════════════
   右侧全息属性抽屉 (Learn Panel) 过渡动画
   ══════════════════════════════════════════════════════════ */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

/* Domain Group 结界节点 */
.code-domain-group-node {
  width: 100%;
  height: 100%;
  padding: 8px 12px;
  pointer-events: auto;
  cursor: pointer;
}

.code-domain-group-label {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 6px;
  background: rgba(15, 17, 21, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.code-graph-flow :deep(.vue-flow__node-group) {
  padding: 0 !important;
  border-radius: 16px !important;
  border: none !important;
  background: transparent !important;
}

/* ══════════════════════════════════════════════════════════
   Persona 切换器
   ══════════════════════════════════════════════════════════ */
.persona-switcher {
  display: flex;
  gap: 1px;
  background: rgba(15, 17, 21, 0.85);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(55, 65, 81, 0.5);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 0 20px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.persona-btn {
  padding: 6px 12px;
  font-size: 10px;
  font-weight: 600;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  color: #64748b;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.03em;
  white-space: nowrap;
}

.persona-btn:hover {
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.04);
}

.persona-btn-active {
  padding: 6px 12px;
  font-size: 10px;
  font-weight: 700;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  color: #e2e8f0;
  background: rgba(59, 130, 246, 0.15);
  border: none;
  cursor: pointer;
  box-shadow: inset 0 -2px 0 #3b82f6;
  letter-spacing: 0.03em;
  white-space: nowrap;
}

/* ══════════════════════════════════════════════════════════
   过滤面板
   ══════════════════════════════════════════════════════════ */
.filter-toggle-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 10px;
  font-weight: 600;
  color: #94a3b8;
  background: rgba(15, 17, 21, 0.85);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(55, 65, 81, 0.5);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 0 12px rgba(0, 0, 0, 0.3);
}

.filter-toggle-btn:hover {
  color: #e2e8f0;
  border-color: rgba(59, 130, 246, 0.4);
  box-shadow: 0 0 16px rgba(59, 130, 246, 0.15);
}

.filter-count-badge {
  font-size: 8px;
  padding: 1px 4px;
  border-radius: 4px;
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
  font-weight: 700;
}

.filter-panel {
  width: 220px;
  background: rgba(15, 17, 21, 0.92);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(55, 65, 81, 0.5);
  border-radius: 10px;
  box-shadow: 0 0 30px rgba(0, 0, 0, 0.5), 0 0 1px rgba(59, 130, 246, 0.3);
  overflow: hidden;
}

.filter-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(55, 65, 81, 0.3);
}

.filter-action-btn {
  font-size: 9px;
  color: #64748b;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  padding: 2px 6px;
  border-radius: 3px;
  transition: all 0.15s;
}

.filter-action-btn:hover {
  color: #e2e8f0;
  background: rgba(255, 255, 255, 0.06);
}

.filter-panel-body {
  padding: 6px 8px;
  max-height: 280px;
  overflow-y: auto;
}

.filter-checkbox-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 6px;
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.15s;
}

.filter-checkbox-row:hover {
  background: rgba(255, 255, 255, 0.03);
}

.filter-checkbox {
  width: 12px;
  height: 12px;
  accent-color: #3b82f6;
  cursor: pointer;
  border-radius: 2px;
}

.filter-layer-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.filter-layer-label {
  font-size: 10px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-weight: 600;
  flex: 1;
}

.filter-layer-count {
  font-size: 9px;
  color: #475569;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

/* 过滤面板滑入动画 */
.filter-slide-enter-active {
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.filter-slide-leave-active {
  transition: all 0.2s cubic-bezier(0.4, 0, 1, 1);
}
.filter-slide-enter-from {
  opacity: 0;
  transform: translateY(-8px) scale(0.95);
}
.filter-slide-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.97);
}

/* ══════════════════════════════════════════════════════════
   Domain Group 折叠样式
   ══════════════════════════════════════════════════════════ */
.code-domain-collapsed {
  cursor: pointer !important;
  pointer-events: auto !important;
}

.code-domain-label-collapsed {
  top: 50% !important;
  right: 50% !important;
  transform: translate(50%, -50%) !important;
  background: rgba(30, 58, 138, 0.5) !important;
  border-color: rgba(59, 130, 246, 0.6) !important;
  white-space: nowrap;
}

.code-domain-collapsed-hint {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 8px;
  color: rgba(96, 165, 250, 0.5);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  pointer-events: none;
}
</style>
