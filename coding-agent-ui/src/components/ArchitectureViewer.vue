<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { VueFlow, useVueFlow, Position, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { layoutGraph } from '../utils/elkLayout.js'

const props = defineProps({
  visible: Boolean,
  graphData: {
    type: Object,
    default: () => ({ nodes: [], edges: [] })
  },
  activeTourNodeId: {
    type: String,
    default: null
  }
})
const emit = defineEmits(['close', 'nodeClick'])

const loading = ref(false)
const isReady = ref(false)
const error = ref(null)
const layoutedNodes = ref([])
const layoutedEdges = ref([])
const selectedNode = ref(null)
const learnNode = ref(null)
const searchQuery = ref('')
const searchInputRef = ref(null)

// ── Learn Panel Tab 状态 ──
const activeTab = ref('ast')  // 'ast' | 'code'
const sourceCodeContent = ref('')
const sourceCodeLoading = ref(false)

const { fitView, setCenter } = useVueFlow()

// ── Diff Mode 状态 ──
const isDiffMode = ref(false)

// ── 容器折叠状态机 ──
const collapsedGroups = ref(new Set())

// ── 角色自适应 UI (Persona) ──
const currentPersona = ref('dev')  // 'manager' | 'dev' | 'geek'

// ── 层级过滤器 (Layer Filter) ──
const availableLayers = ref([])
const visibleLayers = ref([])
const showFilterPanel = ref(false)

// 层级配色
const LAYER_COLORS = {
  api:           { color: '#f59e0b', bg: '#2e1e0e', label: 'API Layer' },
  service:       { color: '#3b82f6', bg: '#0e1e2e', label: 'Service Layer' },
  domain:        { color: '#8b5cf6', bg: '#1e0e2e', label: 'Domain Layer' },
  data:          { color: '#10b981', bg: '#0e2e1e', label: 'Data Layer' },
  database:      { color: '#10b981', bg: '#0e2e1e', label: 'Database Layer' },
  infrastructure:{ color: '#94a3b8', bg: '#1e2230', label: 'Infrastructure' },
  ui:            { color: '#ec4899', bg: '#2e0e1e', label: 'UI Layer' },
  config:        { color: '#64748b', bg: '#1e2230', label: 'Config Layer' },
  unknown:       { color: '#475569', bg: '#1e1e1e', label: 'Unknown' },
}

function getLayerStyle(layer) {
  return LAYER_COLORS[layer] || LAYER_COLORS.unknown
}

// ── Persona 自动折叠逻辑 ──
watch(currentPersona, (newRole) => {
  // 收集所有 domain group ID
  const allGroupIds = []
  const rawNodes = props.graphData?.nodes || []
  const groupSet = new Set()
  rawNodes.forEach(n => {
    const cid = n.cluster_id || (n.data && n.data.cluster_id)
    if (cid) groupSet.add(String(cid))
  })
  groupSet.forEach(id => allGroupIds.push(id))

  if (newRole === 'manager') {
    // 架构师视角：全部折叠，只看模块大框
    collapsedGroups.value = new Set(allGroupIds)
  } else if (newRole === 'geek') {
    // 极客视角：全部展开，细致入微
    collapsedGroups.value = new Set()
  } else {
    // 开发视角：适度展开（暂全展开）
    collapsedGroups.value = new Set()
  }
  renderGraph()
})

// ── Path Finder 状态 ──
const selectedPathNodes = ref([])   // 最多 2 个 nodeId：[起点, 终点]
const highlightedPath = ref({ nodeIds: new Set(), edgeIds: new Set() })
const hasHighlightedPath = computed(() => highlightedPath.value.nodeIds.size > 0)

// ── 聚类调色板 ──
const CLUSTER_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#ef4444', '#14b8a6']
function getClusterColor(clusterId) {
  if (!clusterId) return '#6b7280'
  let hash = 0
  for (let i = 0; i < String(clusterId).length; i++) hash = String(clusterId).charCodeAt(i) + ((hash << 5) - hash)
  return CLUSTER_COLORS[Math.abs(hash) % CLUSTER_COLORS.length]
}

const TYPE_CONFIG = {
  file:     { color: '#06b6d4', bg: '#0e2a38', icon: '📄', label: 'File' },
  class:    { color: '#a78bfa', bg: '#1e1538', icon: '📦', label: 'Class' },
  function: { color: '#34d399', bg: '#0e2e1e', icon: '⚡', label: 'Function' },
  module:   { color: '#f59e0b', bg: '#2e1e0e', icon: '🔧', label: 'Module' },
  service:  { color: '#f472b6', bg: '#2e0e1e', icon: '🌐', label: 'Service' },
  config:   { color: '#94a3b8', bg: '#1e2230', icon: '⚙️', label: 'Config' },
}

const EDGE_STYLE = {
  contains: { color: '#334155', width: 1, style: 'dashed', label: 'contains' },
  imports:  { color: '#f59e0b', width: 1.5, style: 'solid', label: 'imports' },
  calls:    { color: '#34d399', width: 2, style: 'solid', label: 'calls' },
  inherits: { color: '#a78bfa', width: 2, style: 'solid', label: 'inherits' },
}

function getTypeConfig(type) {
  return TYPE_CONFIG[(type || '').toLowerCase()] || TYPE_CONFIG.function
}

// ── ELK 嵌套树状布局（替代力导向，恢复思维导图式展开） ──

function groupNodesByFile(nodes) {
  const groups = new Map()
  const orphans = []

  for (const node of nodes) {
    const nodeType = (node.type || '').toLowerCase()
    const parent = extractParentNodeId(node)
    if (parent) {
      if (!groups.has(parent)) groups.set(parent, [])
      groups.get(parent).push(node)
    } else if (nodeType === 'file') {
      if (!groups.has(node.id)) groups.set(node.id, [])
      groups.get(node.id).unshift(node)
    } else {
      orphans.push(node)
    }
  }

  return { groups, orphans }
}

function extractParentNodeId(node) {
  // 后端节点 ID 格式: "rel/path.java::FunctionName" 或 "rel/path.java::ClassName.methodName"
  // 文件节点 ID 格式: "rel/path.java"
  // 需要从 :: 分割处提取文件路径作为父节点 ID
  const doubleColonIdx = node.id.indexOf('::')
  if (doubleColonIdx > 0) {
    const nodeType = (node.type || '').toLowerCase()
    if (nodeType === 'function' || nodeType === 'class' || nodeType === 'method' || nodeType === 'interface') {
      return node.id.substring(0, doubleColonIdx)
    }
  }
  return null
}

async function renderGraph() {
  if (!props.graphData?.nodes?.length) return

  loading.value = true
  isReady.value = false
  error.value = null

  try {
    const rawNodes = props.graphData.nodes
    const rawEdges = props.graphData.edges || []
    const collapsed = collapsedGroups.value
    const layers = visibleLayers.value

    // 自动收集所有层级
    const layerSet = new Set()
    rawNodes.forEach(n => {
      const layer = n.layer || (n.data && n.data.layer) || 'unknown'
      layerSet.add(layer)
    })
    const detectedLayers = Array.from(layerSet).sort()
    // 首次加载时初始化 availableLayers 和 visibleLayers
    if (availableLayers.value.length === 0 || availableLayers.value.join(',') !== detectedLayers.join(',')) {
      availableLayers.value = detectedLayers
      if (visibleLayers.value.length === 0) {
        visibleLayers.value = [...detectedLayers]
      }
    }

    const tempNodes = []
    const groupSet = new Set()

    // 1. 收集所有 cluster_id，生成 Domain Group 结界
    rawNodes.forEach(n => {
      const cid = n.cluster_id || (n.data && n.data.cluster_id)
      if (cid) groupSet.add(cid)
    })

    Array.from(groupSet).forEach(groupId => {
      const clusterName = rawNodes.find(n =>
        (n.cluster_id || (n.data && n.data.cluster_id)) === groupId
      )?.cluster_name || rawNodes.find(n =>
        (n.cluster_id || (n.data && n.data.cluster_id)) === groupId
      )?.data?.cluster_name || groupId

      const isCollapsed = collapsed.has(String(groupId))

      tempNodes.push({
        id: String(groupId),
        type: 'group',
        position: { x: 0, y: 0 },
        style: {
          backgroundColor: isCollapsed ? 'rgba(30, 58, 138, 0.12)' : 'rgba(30, 58, 138, 0.05)',
          border: isCollapsed ? '2px solid rgba(59, 130, 246, 0.8)' : '2px dashed rgba(59, 130, 246, 0.6)',
          borderRadius: '16px',
          zIndex: -1,
          ...(isCollapsed ? { width: '280px', height: '80px' } : {}),
        },
        data: {
          label: isCollapsed ? `📦 ${clusterName} (➕)` : `📦 领域聚合: ${clusterName} (➖)`,
          nodeType: 'domain-group',
          color: '#3b82f6',
          bg: 'rgba(30, 58, 138, 0.05)',
          icon: '📦',
          isDomainGroup: true,
          isCollapsed,
        },
      })
    })

    // 2. 处理文件组和业务节点（全部扁平，不设 parentNode）
    const { groups: fileGroups, orphans } = groupNodesByFile(rawNodes)

    for (const [groupId, groupNodes] of fileGroups) {
      const fileNode = groupNodes.find(n => (n.type || '').toLowerCase() === 'file')
      const childNodes = groupNodes.filter(n => (n.type || '').toLowerCase() !== 'file')
      const cfg = getTypeConfig(fileNode?.type || 'file')

      // 文件节点：如果所属 domain 被折叠，跳过
      if (fileNode) {
        const fileCid = fileNode.cluster_id || fileNode.data?.cluster_id
        if (fileCid && collapsed.has(String(fileCid))) {
          continue
        }

        // 层级过滤：如果文件节点的层级不在可见列表中，跳过
        const fileLayer = fileNode.layer || fileNode.data?.layer || 'unknown'
        if (!layers.includes(fileLayer)) {
          continue
        }

        tempNodes.push({
          id: fileNode.id,
          position: { x: 0, y: 0 },
          data: {
            label: fileNode.name || fileNode.id,
            nodeType: 'file',
            color: cfg.color,
            bg: cfg.bg,
            icon: cfg.icon,
            file: fileNode.file || '',
            diffStatus: fileNode.diff_status || null,
            clusterId: fileNode.cluster_id || fileNode.data?.cluster_id || null,
            clusterName: fileNode.cluster_name || fileNode.data?.cluster_name || null,
            extra: fileNode,
          },
          style: { width: '260px', height: '60px' },
          sourcePosition: Position.BOTTOM,
          targetPosition: Position.TOP,
        })
      }

      for (const cn of childNodes) {
        const cnCfg = getTypeConfig(cn.type)
        const cid = cn.cluster_id || cn.data?.cluster_id
        const cName = cn.cluster_name || cn.data?.cluster_name

        // 如果所属 domain 被折叠，跳过
        if (cid && collapsed.has(String(cid))) continue

        // 层级过滤
        const cnLayer = cn.layer || cn.data?.layer || 'unknown'
        if (!layers.includes(cnLayer)) continue

        tempNodes.push({
          id: cn.id,
          position: { x: 0, y: 0 },
          data: {
            label: cn.name || cn.id,
            nodeType: cn.type,
            color: cnCfg.color,
            bg: cnCfg.bg,
            icon: cnCfg.icon,
            file: cn.file || '',
            diffStatus: cn.diff_status || null,
            clusterId: cid || null,
            clusterName: cName || null,
            extra: cn,
          },
          style: {
            width: Math.max(160, Math.min(280, (cn.name || cn.id).length * 8 + 40)) + 'px',
            height: ((cn.type || '').toLowerCase() === 'class' ? 48 : 40) + 'px',
          },
          sourcePosition: Position.BOTTOM,
          targetPosition: Position.TOP,
          _fileGroup: fileNode ? fileNode.id : null,
        })
      }
    }

    for (const orphan of orphans) {
      const oCfg = getTypeConfig(orphan.type)
      const cid = orphan.cluster_id || orphan.data?.cluster_id
      const cName = orphan.cluster_name || orphan.data?.cluster_name

      // 如果所属 domain 被折叠，跳过
      if (cid && collapsed.has(String(cid))) continue

      // 层级过滤
      const oLayer = orphan.layer || orphan.data?.layer || 'unknown'
      if (!layers.includes(oLayer)) continue

      tempNodes.push({
        id: orphan.id,
        position: { x: 0, y: 0 },
        data: {
          label: orphan.name || orphan.id,
          nodeType: orphan.type,
          color: oCfg.color,
          bg: oCfg.bg,
          icon: oCfg.icon,
          file: orphan.file || '',
          diffStatus: orphan.diff_status || null,
          clusterId: cid || null,
          clusterName: cName || null,
          extra: orphan,
        },
        style: {
          width: Math.max(160, Math.min(280, (orphan.name || orphan.id).length * 8 + 40)) + 'px',
          height: ((orphan.type || '').toLowerCase() === 'class' ? 48 : 40) + 'px',
        },
        sourcePosition: Position.RIGHT,
        targetPosition: Position.LEFT,
      })
    }

    // 3. 给有 cluster_id 的节点标记 Domain Group 归属
    tempNodes.forEach(n => {
      if (n.type !== 'group' && !n._domainGroup) {
        const cid = n.data?.clusterId
        if (cid && groupSet.has(cid)) {
          n._domainGroup = String(cid)
        }
      }
    })

    // 4. 连线聚合 (Edge Aggregation)
    //    构建节点 ID → 所属 domain group 的映射
    const nodeToGroup = new Map()
    for (const n of tempNodes) {
      if (n.type !== 'group' && n._domainGroup) {
        nodeToGroup.set(String(n.id), String(n._domainGroup))
      }
    }

    const visibleIds = new Set(tempNodes.map(n => String(n.id)))
    const edgeAggregationMap = new Map() // "source→target" → { source, target, count, types }

    for (const edge of rawEdges) {
      let sourceId = String(edge.source)
      let targetId = String(edge.target)

      // 如果 source 节点被折叠（不在可见节点中），重定向到其所属 group
      if (!visibleIds.has(sourceId)) {
        const group = nodeToGroup.get(sourceId)
        if (group && collapsed.has(group)) {
          sourceId = group
        } else {
          continue // source 不在图中，跳过
        }
      }

      // 如果 target 节点被折叠，重定向到其所属 group
      if (!visibleIds.has(targetId)) {
        const group = nodeToGroup.get(targetId)
        if (group && collapsed.has(group)) {
          targetId = group
        } else {
          continue // target 不在图中，跳过
        }
      }

      // source === target 说明是折叠模块内部的调用，抛弃
      if (sourceId === targetId) continue

      // 聚合相同 source→target 的边
      const edgeKey = `${sourceId}→${targetId}`
      if (edgeAggregationMap.has(edgeKey)) {
        const existing = edgeAggregationMap.get(edgeKey)
        existing.count++
        const edgeType = (edge.type || '').toLowerCase()
        if (edgeType && !existing.types.includes(edgeType)) {
          existing.types.push(edgeType)
        }
      } else {
        edgeAggregationMap.set(edgeKey, {
          source: sourceId,
          target: targetId,
          count: 1,
          types: [(edge.type || '').toLowerCase()].filter(Boolean),
          diffStatus: edge.diff_status || null,
        })
      }
    }

    const tempEdges = []
    let edgeIdx = 0
    for (const [, agg] of edgeAggregationMap) {
      // 确定主边类型（优先 calls > imports > contains）
      const primaryType = agg.types.includes('calls') ? 'calls'
        : agg.types.includes('imports') ? 'imports'
        : agg.types[0] || 'contains'
      const style = EDGE_STYLE[primaryType] || EDGE_STYLE.contains
      const isAggregated = agg.count > 1

      tempEdges.push({
        id: `e-${agg.source}-${agg.target}-${edgeIdx++}`,
        source: agg.source,
        target: agg.target,
        type: 'smoothstep',
        animated: primaryType === 'calls',
        diffStatus: agg.diffStatus,
        style: {
          stroke: isAggregated ? '#f59e0b' : style.color,
          strokeWidth: isAggregated ? Math.min(2 + agg.count * 0.5, 5) : style.width,
          strokeDasharray: style.style === 'dashed' ? '5 5' : undefined,
        },
        label: isAggregated ? `${primaryType} ×${agg.count}` : (primaryType !== 'contains' ? primaryType : undefined),
        labelStyle: { fill: isAggregated ? '#f59e0b' : style.color, fontSize: '9px', fontWeight: 600 },
        labelBgStyle: { fill: '#0a0a0a', stroke: isAggregated ? '#f59e0b' : style.color, strokeWidth: 0.5, fillOpacity: 0.9 },
        labelBgPadding: [4, 6],
        labelBgBorderRadius: 3,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: isAggregated ? '#f59e0b' : style.color,
          width: 12,
          height: 12,
        },
      })
    }

    // 5. 调用 ELK 扁平布局引擎
    const finalNodes = await layoutGraph(tempNodes, tempEdges)

    // 6. 注入聚类光晕色
    finalNodes.forEach(n => {
      const clusterId = n.data?.clusterId
      if (clusterId && !n._domainGroup) {
        const glowColor = getClusterColor(clusterId)
        n.style = {
          ...n.style,
          boxShadow: `0 0 15px ${glowColor}30`,
        }
      }
    })

    // 7. 最终上墙
    layoutedNodes.value = finalNodes
    layoutedEdges.value = tempEdges
    isReady.value = true

    // 8. 渲染完成后自动缩放居中
    nextTick(() => {
      setTimeout(() => fitView({ duration: 800, padding: 0.2 }), 100)
    })
  } catch (err) {
    console.error('布局计算失败:', err)
    error.value = `布局计算失败: ${err.message}`
  } finally {
    loading.value = false
  }
}

// 双击折叠/展开结界
function onNodeDoubleClick(event) {
  const node = event.node
  if (!node || node.type !== 'group') return
  if (!node.data?.isDomainGroup) return

  const id = String(node.id)
  const newCollapsed = new Set(collapsedGroups.value)
  if (newCollapsed.has(id)) {
    newCollapsed.delete(id)
  } else {
    newCollapsed.add(id)
  }
  collapsedGroups.value = newCollapsed
  renderGraph()
}

watch(() => props.graphData, () => {
  if (props.visible) renderGraph()
}, { deep: true })

watch(() => props.visible, (v) => {
  if (v && props.graphData?.nodes?.length) {
    nextTick(() => renderGraph())
  }
})

// ── AI 沉浸式漫游导览状态机 ──
const isTouring = ref(false)
const currentTourIndex = ref(0)
const tourSteps = ref([])

// 当前漫游焦点节点 ID（内部 + 外部 prop 合一）
const activeTourNodeId = computed(() => {
  if (isTouring.value && tourSteps.value.length > 0) {
    return tourSteps.value[currentTourIndex.value]?.id || null
  }
  return props.activeTourNodeId
})

// 从布局后的节点中生成漫游路线
function generateTourSteps() {
  const businessNodes = layoutedNodes.value.filter(n => n.type !== 'group')
  if (!businessNodes.length) { tourSteps.value = []; return }

  // 按类型优先级挑选关键节点：class > service > function > file
  const typePriority = { class: 0, service: 1, function: 2, module: 3, file: 4, config: 5 }
  const sorted = [...businessNodes].sort((a, b) => {
    const pa = typePriority[(a.data?.nodeType || '').toLowerCase()] ?? 9
    const pb = typePriority[(b.data?.nodeType || '').toLowerCase()] ?? 9
    return pa - pb
  })

  // 最多取 8 个关键节点
  const picked = sorted.slice(0, Math.min(8, sorted.length))
  tourSteps.value = picked.map(n => ({
    id: n.id,
    label: n.data?.label || n.id,
    nodeType: n.data?.nodeType || '',
    icon: n.data?.icon || '',
    color: n.data?.color || '#06b6d4',
  }))
}

// 运镜引擎：监听漫游状态和步骤变化
watch([isTouring, currentTourIndex], ([touring, index]) => {
  if (!isReady.value) return

  if (touring && tourSteps.value.length > 0) {
    const targetId = tourSteps.value[index]?.id
    if (!targetId) return

    const targetNode = layoutedNodes.value.find(n => String(n.id) === String(targetId))
    if (!targetNode) return

    const w = parseFloat(String(targetNode.style?.width || '240').replace('px', '')) || 240
    const h = parseFloat(String(targetNode.style?.height || '40').replace('px', '')) || 40
    const cx = targetNode.position.x + w / 2
    const cy = targetNode.position.y + h / 2

    setCenter({ x: cx, y: cy, zoom: 1.5, duration: 1200 })
  } else {
    fitView({ duration: 800, padding: 0.2 })
  }
})

// 外部 prop 驱动的运镜（兼容旧逻辑）
watch(() => props.activeTourNodeId, (nodeId) => {
  if (isTouring.value) return // 内部漫游优先
  if (!isReady.value || !nodeId) {
    if (!nodeId) fitView({ duration: 800, padding: 0.2 })
    return
  }

  const targetNode = layoutedNodes.value.find(n => String(n.id) === String(nodeId))
  if (!targetNode) return

  const w = parseFloat(String(targetNode.style?.width || '240').replace('px', '')) || 240
  const h = parseFloat(String(targetNode.style?.height || '40').replace('px', '')) || 40
  const cx = targetNode.position.x + w / 2
  const cy = targetNode.position.y + h / 2

  setCenter({ x: cx, y: cy, zoom: 1.4, duration: 1200 })
})

// 漫游控制函数
function startTour() {
  generateTourSteps()
  if (tourSteps.value.length === 0) return
  currentTourIndex.value = 0
  isTouring.value = true
  searchQuery.value = '' // 清空搜索避免冲突
}

function stopTour() {
  isTouring.value = false
  currentTourIndex.value = 0
}

function tourPrev() {
  if (currentTourIndex.value > 0) currentTourIndex.value--
}

function tourNext() {
  if (currentTourIndex.value < tourSteps.value.length - 1) currentTourIndex.value++
}

// 别名：模板中使用的 prevStep / nextStep
const prevStep = tourPrev
const nextStep = tourNext

const stats = computed(() => {
  const nodes = props.graphData?.nodes || []
  const edges = props.graphData?.edges || []
  const byType = {}
  for (const n of nodes) {
    byType[n.type] = (byType[n.type] || 0) + 1
  }
  const byEdge = {}
  for (const e of edges) {
    byEdge[e.type] = (byEdge[e.type] || 0) + 1
  }
  return { totalNodes: nodes.length, totalEdges: edges.length, byType, byEdge }
})

const filteredNodes = computed(() => {
  const hasSearch = !!searchQuery.value
  const hasTour = !!activeTourNodeId.value
  const hasDiff = isDiffMode.value

  // 无搜索、无导览、无 Diff → 原样返回
  if (!hasSearch && !hasTour && !hasDiff) return layoutedNodes.value

  const q = searchQuery.value.toLowerCase()

  // ── Diff 模式：优先级最高 ──
  if (hasDiff && !hasSearch && !hasTour) {
    return layoutedNodes.value.map(n => {
      const status = n.data?.diffStatus || n.data?.diff_status || n.data?.extra?.diff_status

      if (status === 'added') {
        return {
          ...n,
          style: {
            ...n.style,
            opacity: 1,
            borderColor: '#10b981',
            borderWidth: '2px',
            borderStyle: 'solid',
            boxShadow: '0 0 25px rgba(16, 185, 129, 0.6)',
          },
        }
      }

      if (status === 'removed' || status === 'deleted') {
        return {
          ...n,
          style: {
            ...n.style,
            opacity: 0.8,
            borderColor: '#ef4444',
            borderWidth: '2px',
            borderStyle: 'dashed',
            boxShadow: '0 0 25px rgba(239, 68, 68, 0.6)',
          },
        }
      }

      if (status === 'modified') {
        return {
          ...n,
          style: {
            ...n.style,
            opacity: 1,
            borderColor: '#f59e0b',
            borderWidth: '2px',
            borderStyle: 'solid',
            boxShadow: '0 0 25px rgba(245, 158, 11, 0.6)',
          },
        }
      }

      // unchanged 或未标记 → 极度暗化 + 灰度
      return {
        ...n,
        style: {
          ...n.style,
          opacity: 0.15,
          filter: 'grayscale(100%)',
        },
      }
    })
  }

  // ── 搜索匹配 ──
  const searchMatchedIds = new Set()
  if (hasSearch) {
    for (const n of layoutedNodes.value) {
      if (n.type === 'group') continue
      const label = (n.data?.label || '').toLowerCase()
      const nodeType = (n.data?.nodeType || '').toLowerCase()
      if (label.includes(q) || nodeType.includes(q)) {
        searchMatchedIds.add(String(n.id))
      }
    }
  }

  // ── 导览匹配：当前节点 + 直接相连节点 ──
  const tourFocusIds = new Set()
  const tourGroupIds = new Set()
  if (hasTour) {
    tourFocusIds.add(String(activeTourNodeId.value))
    for (const e of layoutedEdges.value) {
      if (String(e.source) === String(activeTourNodeId.value)) tourFocusIds.add(String(e.target))
      if (String(e.target) === String(activeTourNodeId.value)) tourFocusIds.add(String(e.source))
    }
    // 导览节点所属结界
    for (const n of layoutedNodes.value) {
      if (tourFocusIds.has(String(n.id)) && n._domainGroup) {
        tourGroupIds.add(n._domainGroup)
      }
    }
  }

  // ── 搜索命中的结界 ──
  const searchGroupIds = new Set()
  if (hasSearch) {
    for (const n of layoutedNodes.value) {
      if (n.type === 'group') continue
      if (searchMatchedIds.has(String(n.id)) && n._domainGroup) {
        searchGroupIds.add(n._domainGroup)
      }
    }
  }

  // ── Diff 变更节点集合 ──
  const diffChangedIds = new Set()
  if (hasDiff) {
    for (const n of layoutedNodes.value) {
      const status = n.data?.diffStatus || n.data?.diff_status || n.data?.extra?.diff_status
      if (status === 'added' || status === 'removed' || status === 'deleted' || status === 'modified') {
        diffChangedIds.add(String(n.id))
      }
    }
  }

  // ── 综合样式 ──
  return layoutedNodes.value.map(n => {
    // 结界节点
    if (n.type === 'group') {
      const searchHit = hasSearch && searchGroupIds.has(String(n.id))
      const tourHit = hasTour && tourGroupIds.has(String(n.id))
      if (searchHit || tourHit) {
        return { ...n, style: { ...n.style, opacity: 0.8 } }
      }
      if (hasSearch || hasTour) {
        return { ...n, style: { ...n.style, opacity: 0.1 } }
      }
      if (hasDiff) {
        return { ...n, style: { ...n.style, opacity: 0.15, filter: 'grayscale(100%)' } }
      }
      return n
    }

    const nid = String(n.id)
    const isSearchHit = hasSearch && searchMatchedIds.has(nid)
    const isTourHit = hasTour && tourFocusIds.has(nid)
    const isDiffChanged = hasDiff && diffChangedIds.has(nid)

    // Diff 变更节点高亮（与搜索/导览叠加）
    if (isDiffChanged) {
      const status = n.data?.diffStatus || n.data?.diff_status || n.data?.extra?.diff_status
      let diffStyle = {}
      if (status === 'added') {
        diffStyle = { borderColor: '#10b981', borderWidth: '2px', borderStyle: 'solid', boxShadow: '0 0 25px rgba(16, 185, 129, 0.6)', opacity: 1 }
      } else if (status === 'removed' || status === 'deleted') {
        diffStyle = { borderColor: '#ef4444', borderWidth: '2px', borderStyle: 'dashed', boxShadow: '0 0 25px rgba(239, 68, 68, 0.6)', opacity: 0.8 }
      } else if (status === 'modified') {
        diffStyle = { borderColor: '#f59e0b', borderWidth: '2px', borderStyle: 'solid', boxShadow: '0 0 25px rgba(245, 158, 11, 0.6)', opacity: 1 }
      }
      // 如果同时命中搜索/导览，叠加发光
      if (isSearchHit) {
        diffStyle.boxShadow = (diffStyle.boxShadow || '') + ', 0 0 25px rgba(59,130,246,0.9)'
      }
      if (hasTour && nid === String(activeTourNodeId.value)) {
        diffStyle.boxShadow = (diffStyle.boxShadow || '') + ', 0 0 30px rgba(168,85,247,0.9)'
        diffStyle.zIndex = 200
      }
      return { ...n, style: { ...n.style, ...diffStyle } }
    }

    // 导览当前节点：最强高亮
    if (hasTour && nid === String(activeTourNodeId.value)) {
      return {
        ...n,
        style: {
          ...n.style,
          opacity: 1,
          boxShadow: '0 0 30px rgba(168,85,247,0.9)',
          zIndex: 200,
        },
      }
    }

    // 导览相邻节点
    if (hasTour && isTourHit) {
      return {
        ...n,
        style: {
          ...n.style,
          opacity: 1,
          boxShadow: '0 0 15px rgba(168,85,247,0.4)',
        },
      }
    }

    // 搜索命中
    if (isSearchHit) {
      return {
        ...n,
        style: {
          ...n.style,
          opacity: 1,
          boxShadow: '0 0 25px rgba(59,130,246,0.9)',
        },
      }
    }

    // 未命中：暗化 + 灰度
    if (hasTour) {
      return {
        ...n,
        style: { ...n.style, opacity: 0.1, filter: 'grayscale(100%)' },
      }
    }

    if (hasDiff) {
      return {
        ...n,
        style: { ...n.style, opacity: 0.15, filter: 'grayscale(100%)' },
      }
    }

    return {
      ...n,
      style: { ...n.style, opacity: 0.15 },
    }
  })
})

const filteredEdges = computed(() => {
  const hasSearch = !!searchQuery.value
  const hasTour = !!activeTourNodeId.value
  const hasDiff = isDiffMode.value

  if (!hasSearch && !hasTour && !hasDiff) return layoutedEdges.value

  const q = searchQuery.value.toLowerCase()

  // ── Diff 模式：变更边高亮 ──
  const diffChangedIds = new Set()
  if (hasDiff) {
    for (const n of layoutedNodes.value) {
      const status = n.data?.diffStatus || n.data?.diff_status || n.data?.extra?.diff_status
      if (status === 'added' || status === 'removed' || status === 'deleted' || status === 'modified') {
        diffChangedIds.add(String(n.id))
      }
    }
  }

  // ── 搜索匹配节点 ──
  const searchMatchedIds = new Set()
  if (hasSearch) {
    for (const n of layoutedNodes.value) {
      if (n.type === 'group') continue
      const label = (n.data?.label || '').toLowerCase()
      const nodeType = (n.data?.nodeType || '').toLowerCase()
      if (label.includes(q) || nodeType.includes(q)) {
        searchMatchedIds.add(String(n.id))
      }
    }
  }

  // ── 导览匹配：当前节点直接相连的边 ──
  const tourFocusIds = new Set()
  if (hasTour) {
    tourFocusIds.add(String(activeTourNodeId.value))
  }

  return layoutedEdges.value.map(e => {
    const sourceId = String(e.source)
    const targetId = String(e.target)

    // Diff：与变更节点相连的边 → 按变更类型着色
    if (hasDiff) {
      const sourceChanged = diffChangedIds.has(sourceId)
      const targetChanged = diffChangedIds.has(targetId)
      if (sourceChanged || targetChanged) {
        // 判断边的颜色：如果两端都是 added → 绿色，有 removed → 红色，有 modified → 黄色
        let edgeColor = '#10b981'
        const sourceNode = layoutedNodes.value.find(n => String(n.id) === sourceId)
        const targetNode = layoutedNodes.value.find(n => String(n.id) === targetId)
        const sourceStatus = sourceNode?.data?.diffStatus || sourceNode?.data?.diff_status || sourceNode?.data?.extra?.diff_status
        const targetStatus = targetNode?.data?.diffStatus || targetNode?.data?.diff_status || targetNode?.data?.extra?.diff_status
        if (sourceStatus === 'removed' || sourceStatus === 'deleted' || targetStatus === 'removed' || targetStatus === 'deleted') {
          edgeColor = '#ef4444'
        } else if (sourceStatus === 'modified' || targetStatus === 'modified') {
          edgeColor = '#f59e0b'
        }
        return {
          ...e,
          style: {
            ...e.style,
            stroke: edgeColor,
            opacity: 1,
            strokeWidth: 2.5,
            zIndex: 100,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: edgeColor,
            width: 12,
            height: 12,
          },
        }
      }
      // Diff 模式下未变更的边 → 暗化
      if (!hasSearch && !hasTour) {
        return { ...e, style: { ...e.style, opacity: 0.05 } }
      }
    }

    // 导览：与当前节点直接相连的边 → 亮蓝色发光
    if (hasTour && (tourFocusIds.has(sourceId) || tourFocusIds.has(targetId))) {
      return {
        ...e,
        style: {
          ...e.style,
          stroke: '#3b82f6',
          opacity: 1,
          zIndex: 100,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: '#3b82f6',
          width: 12,
          height: 12,
        },
      }
    }

    // 搜索：source 或 target 命中 → 红色发光
    if (hasSearch && (searchMatchedIds.has(sourceId) || searchMatchedIds.has(targetId))) {
      return {
        ...e,
        style: {
          ...e.style,
          stroke: '#ef4444',
          opacity: 1,
          zIndex: 100,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: '#ef4444',
          width: 12,
          height: 12,
        },
      }
    }

    // 未命中：暗化
    return {
      ...e,
      style: {
        ...e.style,
        opacity: 0.05,
      },
    }
  })
})

const displayNodes = computed(() => {
  const pathNodeIds = highlightedPath.value.nodeIds
  const pathActive = pathNodeIds.size > 0

  return (filteredNodes.value || []).map(n => {
    const isOnPath = pathActive && pathNodeIds.has(String(n.id))
    const isEndpoint = selectedPathNodes.value.includes(String(n.id))

    return {
      ...n,
      class: [
        pathActive && !isOnPath ? 'path-dimmed' : '',
        isOnPath ? 'path-node-active' : '',
        isEndpoint ? 'path-endpoint' : '',
      ].filter(Boolean).join(' '),
    }
  })
})

// ── Diff Mode: 内联样式计算（绕过 Tailwind PurgeCSS 和子元素遮挡） ──
const getDiffNodeStyle = (nodeProps) => {
  if (!isDiffMode.value) return {};
  const status = nodeProps.data?.diffStatus || nodeProps.data?.diff_status || nodeProps.diff_status;
  if (status === 'added') return { border: '2px solid #22c55e', boxShadow: '0 0 20px rgba(34,197,94,0.8)', zIndex: 10 };
  if (status === 'modified') return { border: '2px solid #facc15', boxShadow: '0 0 20px rgba(250,204,21,0.8)', zIndex: 10 };
  if (status === 'impacted') return { border: '2px dashed #f97316', boxShadow: '0 0 15px rgba(249,115,22,0.5)', zIndex: 5 };
  if (status === 'deleted') return { border: '2px solid #ef4444', opacity: 0.5, textDecoration: 'line-through' };
  // 没有任何修改的节点，极度虚化
  return { opacity: 0.15, filter: 'grayscale(100%)', pointerEvents: 'none' };
};

const displayEdges = computed(() => {
  if (!filteredEdges.value) return []
  const pathEdgeIds = highlightedPath.value.edgeIds
  const pathNodeIds = highlightedPath.value.nodeIds
  const pathActive = pathNodeIds.size > 0

  return filteredEdges.value.map(e => {
    const isOnPath = pathActive && pathEdgeIds.has(e.id)

    // 路径高亮优先
    if (isOnPath) {
      return {
        ...e,
        animated: true,
        class: 'path-edge-glow',
        style: { stroke: '#ef4444', strokeWidth: 3 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444', width: 14, height: 14 },
      }
    }

    if (pathActive) {
      return {
        ...e,
        class: 'path-edge-dimmed',
        style: { ...e.style, opacity: 0.15 },
        markerEnd: e.markerEnd,
      }
    }

    return e
  })
})

// ── BFS 最短路径寻路 ──
function findShortestPath(sourceId, targetId, edges) {
  if (sourceId === targetId) return { nodeIds: [sourceId], edgeIds: [] }

  const adj = new Map()
  for (const e of edges) {
    if (!adj.has(e.source)) adj.set(e.source, [])
    adj.get(e.source).push({ target: e.target, edgeId: e.id })
    // 无向图：反向也加入
    if (!adj.has(e.target)) adj.set(e.target, [])
    adj.get(e.target).push({ target: e.source, edgeId: e.id })
  }

  const visited = new Set([sourceId])
  const queue = [[sourceId, [sourceId], []]]

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

  return null
}

function clearPathFinder() {
  selectedPathNodes.value = []
  highlightedPath.value = { nodeIds: new Set(), edgeIds: new Set() }
}

function handleNodeClick(event) {
  const nodeId = event.node?.id
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
    const result = findShortestPath(source, target, layoutedEdges.value)
    if (result) {
      highlightedPath.value = { nodeIds: new Set(result.nodeIds), edgeIds: new Set(result.edgeIds) }
    } else {
      highlightedPath.value = { nodeIds: new Set(), edgeIds: new Set() }
    }
  }
}

function handlePaneClick() {
  selectedNode.value = null
  learnNode.value = null
  clearPathFinder()
}

// ── 全局极客快捷键引擎 ──
function handleGlobalKeydown(e) {
  // 如果正在输入框中，只处理 Esc
  const isInputFocused = document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA'

  // / 键：聚焦搜索框
  if (e.key === '/' && !isInputFocused) {
    e.preventDefault()
    searchInputRef.value?.focus()
    return
  }

  // Esc 键：关闭面板 > 清空搜索 > 退出漫游
  if (e.key === 'Escape') {
    if (learnNode.value) {
      learnNode.value = null
      selectedNode.value = null
    } else if (searchQuery.value) {
      searchQuery.value = ''
      searchInputRef.value?.blur()
    } else if (isTouring.value) {
      stopTour()
    }
    return
  }

  // ← → 键：漫游控制
  if (isTouring.value && !isInputFocused) {
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      tourPrev()
      return
    }
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      tourNext()
      return
    }
  }

  // d 键：切换 Diff 时光机模式
  if (e.key === 'd' && !isInputFocused) {
    isDiffMode.value = !isDiffMode.value
    return
  }
}

onMounted(() => {
  if (props.visible && props.graphData?.nodes?.length) {
    renderGraph()
  }
  document.addEventListener('keydown', handleGlobalKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
})

// ── 源代码动态抓取 ──
async function fetchNodeSourceCode(node) {
  if (!node) return

  const filePath = node.data?.extra?.file_path || node.data?.extra?.file || node.data?.file || ''
  // 从节点 ID 中提取文件路径（格式: "rel/path.py::FunctionName"）
  const nodeId = node.id || ''
  const extractedPath = nodeId.includes('::') ? nodeId.split('::')[0] : nodeId
  const targetPath = filePath || extractedPath

  if (!targetPath || targetPath.includes('::')) {
    sourceCodeContent.value = '/* Source code for this module is not accessible in current context. */'
    return
  }

  sourceCodeLoading.value = true
  sourceCodeContent.value = 'Loading source code...'

  try {
    const resp = await fetch('/api/v1/files?path=' + encodeURIComponent(targetPath))
    if (resp.ok) {
      const data = await resp.json()
      sourceCodeContent.value = data.content || data.text || data.source || '/* Empty response */'
    } else {
      // 降级：尝试直接读取文本
      const textResp = await fetch('/api/v1/files/' + encodeURIComponent(targetPath))
      if (textResp.ok) {
        sourceCodeContent.value = await textResp.text()
      } else {
        sourceCodeContent.value = '/* Source code for this module is not accessible in current context. */'
      }
    }
  } catch {
    sourceCodeContent.value = '/* Source code for this module is not accessible in current context. */'
  } finally {
    sourceCodeLoading.value = false
  }
}

// 监听 learnNode 变化 + activeTab 切换到 code 时触发源码加载
watch(learnNode, (node) => {
  activeTab.value = 'ast'  // 重置到 AST 视图
  sourceCodeContent.value = ''
  if (node && activeTab.value === 'code') {
    fetchNodeSourceCode(node)
  }
})

watch(activeTab, (tab) => {
  if (tab === 'code' && learnNode.value && !sourceCodeContent.value) {
    fetchNodeSourceCode(learnNode.value)
  }
})
</script>

<template>
  <Transition name="arch-slide">
    <div v-if="visible" class="fixed inset-0 z-[100] flex items-center justify-center" @click.self="emit('close')">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>

      <div class="relative w-[1100px] max-w-[95vw] h-[85vh] bg-geek-surface border border-cyan-500/20 shadow-[0_0_40px_rgba(0,255,136,0.06)] rounded-xl flex flex-col">

        <div class="flex items-center justify-between px-5 py-3 border-b border-geek-border shrink-0 bg-geek-bg/50">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-violet-900/40 border border-violet-500/30 flex items-center justify-center text-sm">🏗️</div>
            <div>
              <div class="text-sm font-bold text-violet-400">Architecture Viewer</div>
              <div class="text-[10px] text-geek-text-dim">ELK 正交布局 · 跨文件依赖分析</div>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <button
              @click="isDiffMode = !isDiffMode"
              :class="isDiffMode ? 'bg-orange-600 border-orange-500 shadow-[0_0_10px_rgba(234,88,12,0.8)] text-white' : 'bg-gray-800/90 border-gray-600 text-gray-300'"
              class="px-3 py-1.5 rounded-lg border text-[11px] font-bold transition-all duration-300 cursor-pointer hover:scale-105 flex items-center gap-1.5"
            >
              <span>{{ isDiffMode ? '🔥' : '👁️' }}</span>
              <span>{{ isDiffMode ? 'Diff: ON' : 'Diff' }}</span>
            </button>
            <button @click="emit('close')" class="text-geek-text-dim hover:text-geek-text text-lg leading-none ml-2">×</button>
          </div>
        </div>

        <div class="flex-1 min-h-0 relative bg-[#080c14]">
          <!-- 上帝视角聚焦搜索框 -->
          <div v-if="isReady" class="absolute top-6 left-1/2 -translate-x-1/2 z-50">
            <div class="search-box-glass">
              <input
                ref="searchInputRef"
                v-model="searchQuery"
                placeholder="🔍 探索架构节点 (如 Controller, Service)..."
                class="search-input-glass"
              />
              <button v-if="searchQuery" @click="searchQuery = ''" class="search-clear-btn">×</button>
            </div>
          </div>

          <div v-if="loading" class="absolute inset-0 flex items-center justify-center z-20 bg-[#080c14]/80">
            <div class="text-center">
              <div class="text-violet-400 text-lg mb-2 animate-pulse">⬡</div>
              <div class="text-xs text-geek-text-dim">ELK 布局计算中...</div>
            </div>
          </div>

          <div v-if="error" class="absolute inset-0 flex items-center justify-center z-20 bg-[#080c14]/80">
            <div class="text-center max-w-[80%]">
              <div class="text-red-400 text-lg mb-2">⚠️</div>
              <div class="text-xs text-red-300">{{ error }}</div>
            </div>
          </div>

          <div v-if="!graphData?.nodes?.length && !loading" class="absolute inset-0 flex items-center justify-center z-20">
            <div class="text-center">
              <div class="text-4xl mb-3 opacity-30">🏗️</div>
              <div class="text-xs text-geek-text-dim">暂无架构数据</div>
              <div class="text-[10px] text-geek-text-dim mt-1">运行 project_grapher.py 生成 project_structure.json</div>
            </div>
          </div>

          <VueFlow
            v-if="isReady"
            :nodes="displayNodes"
            :edges="displayEdges"
            :fit-view-on-init="true"
            :default-viewport="{ zoom: 0.7, x: 0, y: 0 }"
            :min-zoom="0.1"
            :max-zoom="3"
            :nodes-draggable="true"
            :nodes-connectable="false"
            :elements-selectable="true"
            class="arch-flow"
            @node-click="handleNodeClick"
            @pane-click="handlePaneClick"
            @node-double-click="onNodeDoubleClick"
          >
            <Background :gap="20" :size="1" pattern-color="#1e293b" />
            <Controls
              position="bottom-left"
              class="!bg-geek-bg/90 !border-geek-border !rounded-lg !shadow-xl"
            />
            <MiniMap
              position="bottom-right"
              :node-color="(n) => n.data?.color || '#06b6d4'"
              :mask-color="'rgba(0,0,0,0.7)'"
              class="!bg-geek-bg/90 !border-geek-border !rounded-lg"
              :pannable="true"
              :zoomable="true"
            />

            <template #node-group="groupNodeProps">
              <!-- DDD 领域聚合结界 -->
              <div v-if="groupNodeProps.data?.isDomainGroup" class="arch-domain-group-node" :class="{ 'arch-domain-collapsed': groupNodeProps.data?.isCollapsed }">
                <div class="arch-domain-group-label" :class="{ 'arch-domain-label-collapsed': groupNodeProps.data?.isCollapsed }">
                  <span class="text-[10px] mr-1">📦</span>
                  <span class="text-[10px] font-bold text-blue-400">{{ groupNodeProps.data?.label }}</span>
                </div>
                <div v-if="groupNodeProps.data?.isCollapsed" class="arch-domain-collapsed-hint">双击展开</div>
              </div>
              <!-- 文件组节点（原有逻辑） -->
              <div
                v-else
                class="arch-group-node"
                :style="{
                  borderColor: groupNodeProps.data?.color + '40',
                  background: 'linear-gradient(135deg, ' + groupNodeProps.data?.bg + 'cc, ' + groupNodeProps.data?.bg + '66)',
                  ...getDiffNodeStyle(groupNodeProps),
                }"
              >
                <!-- Diff Mode 角标 -->
                <div v-if="isDiffMode && groupNodeProps.data?.diffStatus === 'deleted'" class="diff-deleted-x">✕</div>
                <div v-if="isDiffMode && groupNodeProps.data?.diffStatus === 'impacted'" class="diff-impacted-badge">⚠</div>
                <div v-if="isDiffMode && groupNodeProps.data?.diffStatus === 'added'" class="diff-status-tag diff-tag-added">+ADDED</div>
                <div v-if="isDiffMode && groupNodeProps.data?.diffStatus === 'modified'" class="diff-status-tag diff-tag-modified">~MOD</div>
                <div class="arch-group-header" :style="{ borderColor: groupNodeProps.data?.color + '30' }">
                  <span class="text-[10px] mr-1">{{ groupNodeProps.data?.icon }}</span>
                  <span class="text-[11px] font-bold truncate" :style="{ color: groupNodeProps.data?.color }">
                    {{ groupNodeProps.data?.label }}
                  </span>
                </div>
              </div>
            </template>

            <template #node-default="defaultNodeProps">
              <div
                class="arch-default-node"
                :style="{
                  borderColor: defaultNodeProps.data?.color + '60',
                  background: defaultNodeProps.data?.bg,
                  boxShadow: '0 0 12px ' + defaultNodeProps.data?.color + '10',
                  ...getDiffNodeStyle(defaultNodeProps),
                }"
              >
                <!-- Diff Mode 标记 -->
                <div v-if="isDiffMode && defaultNodeProps.data?.diffStatus === 'deleted'" class="diff-deleted-x">✕</div>
                <div v-if="isDiffMode && defaultNodeProps.data?.diffStatus === 'impacted'" class="diff-impacted-badge">⚠</div>
                <div v-if="isDiffMode && defaultNodeProps.data?.diffStatus === 'added'" class="diff-status-tag diff-tag-added">+ADD</div>
                <div v-if="isDiffMode && defaultNodeProps.data?.diffStatus === 'modified'" class="diff-status-tag diff-tag-modified">~MOD</div>
                <span class="text-[10px] mr-1.5 shrink-0">{{ defaultNodeProps.data?.icon }}</span>
                <span class="text-[11px] truncate" :style="{ color: defaultNodeProps.data?.color }">
                  {{ defaultNodeProps.data?.label }}
                </span>
                <span class="text-[8px] ml-auto shrink-0 px-1 py-0.5 rounded opacity-50" :style="{ color: defaultNodeProps.data?.color, background: defaultNodeProps.data?.color + '15' }">
                  {{ defaultNodeProps.data?.nodeType }}
                </span>
              </div>
            </template>
          </VueFlow>

          <div v-if="!isReady && loading" class="absolute inset-0 flex items-center justify-center bg-geek-bg/80 z-50">
            <div class="text-blue-500 font-mono animate-pulse tracking-widest text-lg">
              [ ELK ENGINE CALCULATING DOMAIN ... ]
            </div>
          </div>

          <div class="absolute top-3 left-3 z-10 flex flex-col gap-1.5 pointer-events-none">
            <div class="flex items-center gap-2 text-[9px] bg-geek-bg/80 backdrop-blur-sm border border-geek-border rounded px-2 py-1 pointer-events-auto">
              <span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span><span class="text-geek-text-dim">File</span>
              <span class="w-1.5 h-1.5 rounded-full bg-violet-400"></span><span class="text-geek-text-dim">Class</span>
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span><span class="text-geek-text-dim">Func</span>
            </div>
            <div class="flex items-center gap-2 text-[9px] bg-geek-bg/80 backdrop-blur-sm border border-geek-border rounded px-2 py-1 pointer-events-auto">
              <span class="w-3 h-0.5 bg-amber-400"></span><span class="text-geek-text-dim">imports</span>
              <span class="w-3 h-0.5 bg-emerald-400"></span><span class="text-geek-text-dim">calls</span>
              <span class="w-3 h-0.5 bg-slate-500" style="border-bottom: 1px dashed"></span><span class="text-geek-text-dim">contains</span>
            </div>
            <div class="flex items-center gap-2 text-[9px] bg-geek-bg/80 backdrop-blur-sm border border-geek-border rounded px-2 py-1 pointer-events-auto">
              <kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">Shift</kbd><span class="text-geek-text-dim">+点击寻路</span>
            </div>
            <div class="flex items-center gap-2 text-[9px] bg-geek-bg/80 backdrop-blur-sm border border-geek-border rounded px-2 py-1 pointer-events-auto">
              <kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">/</kbd><span class="text-geek-text-dim">搜索</span>
              <kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">Esc</kbd><span class="text-geek-text-dim">关闭</span>
              <kbd class="px-1 py-0.5 rounded bg-slate-800 border border-slate-600 text-[8px] text-slate-300">←→</kbd><span class="text-geek-text-dim">漫游</span>
            </div>
            <div class="flex items-center gap-2 text-[9px] bg-geek-bg/80 backdrop-blur-sm border border-geek-border rounded px-2 py-1 pointer-events-auto">
              <span class="text-geek-text-dim">双击结界</span><span class="text-blue-400">折叠/展开</span>
            </div>
          </div>

          <!-- 右上角全息控制面板 -->
          <div v-if="isReady" class="absolute top-3 right-3 z-50 flex flex-col gap-2 items-end">
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
                    <button @click="visibleLayers = [...availableLayers]; renderGraph()" class="filter-action-btn">全选</button>
                    <button @click="visibleLayers = []; renderGraph()" class="filter-action-btn">清空</button>
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
                      @change="renderGraph()"
                      class="filter-checkbox"
                    />
                    <span class="filter-layer-dot" :style="{ background: getLayerStyle(layer).color }"></span>
                    <span class="filter-layer-label" :style="{ color: getLayerStyle(layer).color }">
                      {{ getLayerStyle(layer).label }}
                    </span>
                    <span class="filter-layer-count">
                      {{ props.graphData?.nodes?.filter(n => (n.layer || n.data?.layer || 'unknown') === layer).length || 0 }}
                    </span>
                  </label>
                </div>
              </div>
            </Transition>

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
              <div v-if="isDiffMode" class="mt-3 flex flex-col gap-2 text-xs font-mono bg-black/50 p-3 rounded border border-gray-800">
                <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-emerald-500 shadow-[0_0_10px_#10b981]"></span> 新增节点 (Added)</div>
                <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-amber-500 shadow-[0_0_10px_#f59e0b]"></span> 发生修改 (Modified)</div>
                <div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-red-500 shadow-[0_0_10px_#ef4444] border border-dashed"></span> 已被移除 (Removed)</div>
              </div>
            </Transition>
          </div>

          <!-- Path Finder 状态条 -->
          <div v-if="selectedPathNodes.length > 0" class="absolute top-24 right-3 z-10 flex items-center gap-2 text-[9px] bg-black/80 backdrop-blur-sm border border-red-500/40 rounded-md px-2.5 py-1.5 pointer-events-auto">
            <span class="text-red-400 font-bold">PATH</span>
            <div class="flex items-center gap-1">
              <span
                v-for="(nid, idx) in selectedPathNodes"
                :key="nid"
                class="px-1.5 py-0.5 rounded text-[8px] font-mono"
                :class="idx === 0 ? 'bg-emerald-900/60 text-emerald-400 border border-emerald-500/40' : 'bg-red-900/60 text-red-400 border border-red-500/40'"
              >{{ nid.split('::').pop() }}</span>
              <span v-if="idx === 0 && selectedPathNodes.length === 2" class="text-slate-500">→</span>
            </div>
            <span v-if="selectedPathNodes.length === 1" class="text-slate-500">Shift+点击选择终点</span>
            <span v-if="selectedPathNodes.length === 2 && hasHighlightedPath" class="text-emerald-400">{{ highlightedPath.nodeIds.size }} 节点 · {{ highlightedPath.edgeIds.size }} 边</span>
            <span v-if="selectedPathNodes.length === 2 && !hasHighlightedPath" class="text-amber-400">不可达</span>
            <button @click="clearPathFinder" class="ml-1 text-slate-500 hover:text-white text-[10px]">×</button>
          </div>

          <!-- AI 沉浸式漫游导览控制器 -->
          <!-- 已移至最外层容器，z-[9999] -->

          <!-- 右侧全息属性抽屉 (Learn Panel) -->
          <Transition name="slide-right">
            <div v-if="learnNode" class="learn-panel">
              <!-- Header -->
              <div class="learn-header">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="text-sm shrink-0">{{ learnNode.data?.icon }}</span>
                  <span class="text-sm font-bold truncate" :style="{ color: learnNode.data?.color || '#e2e8f0' }">
                    {{ learnNode.data?.label }}
                  </span>
                </div>
                <button @click="learnNode = null" class="learn-close-btn" title="关闭 (Esc)">
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <!-- Tab 切换器 -->
              <div class="learn-tabs">
                <button @click="activeTab = 'ast'" :class="activeTab === 'ast' ? 'learn-tab-active' : 'learn-tab-inactive'" class="learn-tab-btn">SYMBOLS</button>
                <button @click="activeTab = 'code'" :class="activeTab === 'code' ? 'learn-tab-active' : 'learn-tab-inactive'" class="learn-tab-btn">SOURCE CODE</button>
              </div>

              <!-- AST 视图 -->
              <div v-if="activeTab === 'ast'" class="learn-tab-content custom-scrollbar">
                <!-- Node Type Badge -->
                <div class="learn-section">
                  <div class="learn-section-title">IDENTITY</div>
                  <div class="flex flex-wrap gap-1.5">
                    <span class="learn-badge" :style="{ borderColor: learnNode.data?.color + '60', color: learnNode.data?.color, background: learnNode.data?.color + '12' }">
                      {{ learnNode.data?.nodeType }}
                    </span>
                    <span v-if="learnNode.data?.file" class="learn-badge learn-badge-dim">
                      {{ learnNode.data?.file.split('/').pop() }}
                    </span>
                  </div>
                </div>

                <!-- Cluster / Domain -->
                <div v-if="learnNode.data?.clusterName || learnNode._domainGroup" class="learn-section">
                  <div class="learn-section-title">DOMAIN</div>
                  <div class="flex flex-wrap gap-1.5">
                    <span v-if="learnNode.data?.clusterName" class="learn-badge learn-badge-blue">
                      <span class="text-[9px] mr-1">📦</span>{{ learnNode.data?.clusterName }}
                    </span>
                    <span v-if="learnNode._domainGroup" class="learn-badge learn-badge-purple">
                      Group: {{ learnNode._domainGroup }}
                    </span>
                  </div>
                </div>

                <!-- AST Symbols -->
                <div class="learn-section">
                  <div class="learn-section-title">AST SYMBOLS</div>
                  <div v-if="learnNode.data?.extra?.methods?.length || learnNode.data?.extra?.symbols?.length" class="learn-symbols-list">
                    <div
                      v-for="(sym, si) in (learnNode.data?.extra?.symbols || learnNode.data?.extra?.methods || [])"
                      :key="si"
                      class="learn-symbol-item"
                    >
                      <span class="learn-symbol-icon">ƒ</span>
                      <span class="learn-symbol-name">{{ typeof sym === 'string' ? sym : sym.name || sym }}</span>
                    </div>
                  </div>
                  <div v-else class="learn-empty">
                    <span class="text-[10px] text-gray-600">No AST symbols extracted yet.</span>
                  </div>
                </div>

                <!-- Extra Metadata -->
                <div v-if="learnNode.data?.extra?.params?.length || learnNode.data?.extra?.return_type" class="learn-section">
                  <div class="learn-section-title">SIGNATURE</div>
                  <div class="learn-sig-list">
                    <div v-if="learnNode.data?.extra?.params?.length" class="learn-sig-item">
                      <span class="learn-sig-key">params</span>
                      <span class="learn-sig-val">{{ learnNode.data.extra.params.join(', ') }}</span>
                    </div>
                    <div v-if="learnNode.data?.extra?.return_type" class="learn-sig-item">
                      <span class="learn-sig-key">returns</span>
                      <span class="learn-sig-val">{{ learnNode.data.extra.return_type }}</span>
                    </div>
                  </div>
                </div>

                <!-- AI Summary (预留) -->
                <div class="learn-section">
                  <div class="learn-section-title">AI ARCHITECTURE SUMMARY</div>
                  <div class="learn-ai-placeholder">
                    <div class="learn-skeleton-line w-3/4"></div>
                    <div class="learn-skeleton-line w-1/2"></div>
                    <div class="learn-skeleton-line w-5/6"></div>
                    <div class="learn-skeleton-line w-2/3"></div>
                    <div class="text-[10px] text-gray-600 mt-2 italic">Analysis pending...</div>
                  </div>
                </div>
              </div>

              <!-- Code 视图 -->
              <div v-else-if="activeTab === 'code'" class="learn-tab-content">
                <div class="learn-code-viewer">
                  <!-- 终端标题栏 -->
                  <div class="learn-code-titlebar">
                    <div class="flex items-center gap-1.5">
                      <span class="w-2.5 h-2.5 rounded-full bg-red-500/70"></span>
                      <span class="w-2.5 h-2.5 rounded-full bg-yellow-500/70"></span>
                      <span class="w-2.5 h-2.5 rounded-full bg-green-500/70"></span>
                    </div>
                    <span class="text-[9px] text-gray-500 font-mono ml-2 truncate">{{ learnNode.data?.extra?.file_path || learnNode.id }}</span>
                  </div>
                  <!-- 代码内容 -->
                  <div v-if="sourceCodeLoading" class="learn-code-loading">
                    <div class="learn-skeleton-line w-full"></div>
                    <div class="learn-skeleton-line w-5/6"></div>
                    <div class="learn-skeleton-line w-4/6"></div>
                    <div class="learn-skeleton-line w-full"></div>
                    <div class="learn-skeleton-line w-3/4"></div>
                    <div class="text-[10px] text-gray-600 mt-2 italic animate-pulse">Fetching source...</div>
                  </div>
                  <pre v-else class="learn-code-pre custom-scrollbar"><code>{{ sourceCodeContent }}</code></pre>
                </div>
              </div>
            </div>
          </Transition>
        </div>

        <div class="border-t border-geek-border shrink-0 bg-geek-bg/50">
          <div v-if="selectedNode" class="px-4 py-2.5 flex items-start gap-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-[10px]">{{ getTypeConfig(selectedNode.type).icon }}</span>
                <span class="text-xs font-bold" :style="{ color: getTypeConfig(selectedNode.type).color }">{{ selectedNode.name }}</span>
                <span class="text-[9px] px-1.5 py-0.5 rounded bg-geek-bg border border-geek-border text-geek-text-dim">{{ selectedNode.type }}</span>
              </div>
              <div v-if="selectedNode.file" class="text-[10px] text-geek-text-dim truncate">{{ selectedNode.file }}</div>
              <div v-if="selectedNode.params?.length" class="text-[10px] text-geek-text-dim mt-0.5">
                params: {{ selectedNode.params.join(', ') }}
              </div>
              <div v-if="selectedNode.return_type" class="text-[10px] text-geek-text-dim">
                returns: {{ selectedNode.return_type }}
              </div>
              <div v-if="selectedNode.methods?.length" class="text-[10px] text-geek-text-dim mt-0.5">
                methods: {{ selectedNode.methods.join(', ') }}
              </div>
            </div>
            <button @click="selectedNode = null" class="text-geek-text-dim hover:text-geek-text text-xs">×</button>
          </div>

          <div v-else class="px-4 py-2 flex items-center justify-between">
            <div class="flex items-center gap-3 text-[10px] text-geek-text-dim">
              <span>📊 {{ stats.totalNodes }} 节点</span>
              <span>🔗 {{ stats.totalEdges }} 边</span>
              <template v-for="(count, type) in stats.byType" :key="type">
                <span v-if="count" class="flex items-center gap-1">
                  <span class="w-1.5 h-1.5 rounded-full" :style="{ background: getTypeConfig(type).color }"></span>
                  {{ count }} {{ getTypeConfig(type).label }}
                </span>
              </template>
            </div>
            <div class="text-[9px] text-geek-text-dim opacity-50">ELK Layered · Orthogonal</div>
          </div>
        </div>

        <!-- ══════════════════════════════════════════════════════
             AI 沉浸式漫游导览控制器 — 最外层 z-[9999]
             ══════════════════════════════════════════════════════ -->
        <div v-if="isReady && !isTouring" class="absolute bottom-10 left-1/2 -translate-x-1/2 z-[9999]">
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
                {{ tourSteps[currentTourIndex]?.label || 'Unknown Node' }}
              </span>
            </div>

            <div class="flex items-center gap-2 border-l border-gray-700 pl-6">
              <button @click="prevStep" :disabled="currentTourIndex === 0" class="p-2 hover:bg-gray-800 rounded disabled:opacity-30 text-white">⏪</button>
              <button @click="stopTour" class="px-4 py-2 bg-red-500/20 hover:bg-red-500/40 text-red-400 rounded text-sm font-bold transition-colors">⏹ 退出</button>
              <button @click="nextStep" :disabled="currentTourIndex === tourSteps.length - 1" class="p-2 hover:bg-gray-800 rounded disabled:opacity-30 text-white">⏩</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* ══════════════════════════════════════════════════════════
   上帝视角聚焦搜索框 - 极客暗黑玻璃态
   ══════════════════════════════════════════════════════════ */
.search-box-glass {
  position: relative;
  display: flex;
  align-items: center;
  width: 420px;
  background: rgba(10, 10, 20, 0.75);
  backdrop-filter: blur(16px) saturate(1.8);
  -webkit-backdrop-filter: blur(16px) saturate(1.8);
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: 12px;
  box-shadow:
    0 0 20px rgba(59, 130, 246, 0.08),
    0 8px 32px rgba(0, 0, 0, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  transition: border-color 0.3s, box-shadow 0.3s;
}

.search-box-glass:focus-within {
  border-color: rgba(59, 130, 246, 0.6);
  box-shadow:
    0 0 30px rgba(59, 130, 246, 0.15),
    0 8px 32px rgba(0, 0, 0, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.search-input-glass {
  width: 100%;
  padding: 10px 14px;
  background: transparent;
  border: none;
  outline: none;
  color: #e2e8f0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  letter-spacing: 0.02em;
}

.search-input-glass::placeholder {
  color: rgba(148, 163, 184, 0.5);
  font-style: italic;
}

.search-clear-btn {
  position: absolute;
  right: 10px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 6px;
  color: #94a3b8;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.search-clear-btn:hover {
  background: rgba(59, 130, 246, 0.3);
  color: #e2e8f0;
}

/* ══════════════════════════════════════════════════════════
   AI 沉浸式漫游导览控制器
   ══════════════════════════════════════════════════════════ */
.tour-start-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(59, 130, 246, 0.08));
  border: 1px solid rgba(59, 130, 246, 0.4);
  border-radius: 12px;
  color: #93c5fd;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow:
    0 0 20px rgba(59, 130, 246, 0.15),
    0 4px 16px rgba(0, 0, 0, 0.4);
}

.tour-start-btn:hover {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.35), rgba(59, 130, 246, 0.15));
  border-color: rgba(59, 130, 246, 0.7);
  box-shadow:
    0 0 30px rgba(59, 130, 246, 0.25),
    0 4px 16px rgba(0, 0, 0, 0.4);
  transform: translateY(-1px);
}

.tour-panel {
  position: relative;
  width: 480px;
  background: rgba(17, 24, 39, 0.92);
  backdrop-filter: blur(20px) saturate(1.6);
  -webkit-backdrop-filter: blur(20px) saturate(1.6);
  border: 1px solid rgba(107, 114, 128, 0.4);
  border-radius: 14px;
  overflow: hidden;
  box-shadow:
    0 0 30px rgba(59, 130, 246, 0.08),
    0 12px 40px rgba(0, 0, 0, 0.6);
}

.tour-progress-bar {
  height: 2px;
  background: rgba(55, 65, 81, 0.5);
}

.tour-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #60a5fa, #93c5fd);
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.5);
  transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.tour-panel-content {
  padding: 14px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tour-step-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tour-step-badge {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.12);
  border: 1px solid rgba(59, 130, 246, 0.25);
  color: #60a5fa;
  white-space: nowrap;
}

.tour-step-icon {
  font-size: 14px;
}

.tour-step-label {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  font-weight: 700;
  color: #e2e8f0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tour-controls {
  display: flex;
  gap: 8px;
}

.tour-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 14px;
  border-radius: 8px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.tour-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.tour-btn-stop {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #f87171;
}

.tour-btn-stop:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.5);
}

.tour-btn-nav {
  flex: 1;
  background: rgba(59, 130, 246, 0.1);
  border-color: rgba(59, 130, 246, 0.3);
  color: #93c5fd;
}

.tour-btn-nav:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.5);
}

/* ══════════════════════════════════════════════════════════
   右侧全息属性抽屉 (Learn Panel)
   ══════════════════════════════════════════════════════════ */
.learn-panel {
  position: absolute;
  top: 0;
  right: 0;
  height: 100%;
  width: 384px;
  background: rgba(15, 17, 21, 0.95);
  backdrop-filter: blur(24px) saturate(1.5);
  -webkit-backdrop-filter: blur(24px) saturate(1.5);
  border-left: 1px solid rgba(55, 65, 81, 0.6);
  box-shadow: -8px 0 40px rgba(0, 0, 0, 0.5);
  z-index: 60;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.learn-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid rgba(55, 65, 81, 0.4);
  background: rgba(0, 0, 0, 0.2);
}

.learn-close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #f87171;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.learn-close-btn:hover {
  background: rgba(239, 68, 68, 0.18);
  border-color: rgba(239, 68, 68, 0.4);
}

.learn-section {
  padding: 14px 18px;
  border-bottom: 1px solid rgba(55, 65, 81, 0.25);
}

.learn-section-title {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.12em;
  color: #64748b;
  margin-bottom: 10px;
}

.learn-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid;
  white-space: nowrap;
}

.learn-badge-dim {
  border-color: rgba(100, 116, 139, 0.3);
  color: #94a3b8;
  background: rgba(100, 116, 139, 0.08);
}

.learn-badge-blue {
  border-color: rgba(59, 130, 246, 0.3);
  color: #60a5fa;
  background: rgba(59, 130, 246, 0.08);
}

.learn-badge-purple {
  border-color: rgba(168, 85, 247, 0.3);
  color: #c084fc;
  background: rgba(168, 85, 247, 0.08);
}

.learn-symbols-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.learn-symbol-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(34, 211, 153, 0.04);
  border: 1px solid rgba(34, 211, 153, 0.1);
  transition: background 0.15s;
}

.learn-symbol-item:hover {
  background: rgba(34, 211, 153, 0.08);
}

.learn-symbol-icon {
  font-size: 12px;
  font-weight: 700;
  color: #34d399;
  font-style: italic;
  width: 16px;
  text-align: center;
}

.learn-symbol-name {
  font-size: 11px;
  color: #d1d5db;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.learn-empty {
  padding: 12px;
  border-radius: 8px;
  background: rgba(55, 65, 81, 0.1);
  border: 1px dashed rgba(55, 65, 81, 0.3);
  text-align: center;
}

.learn-sig-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.learn-sig-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.learn-sig-key {
  font-size: 10px;
  color: #64748b;
  min-width: 48px;
  flex-shrink: 0;
}

.learn-sig-val {
  font-size: 11px;
  color: #94a3b8;
  word-break: break-all;
}

.learn-ai-placeholder {
  padding: 10px;
  border-radius: 8px;
  background: rgba(168, 85, 247, 0.04);
  border: 1px solid rgba(168, 85, 247, 0.12);
}

/* ══════════════════════════════════════════════════════════
   Learn Panel Tab 切换器
   ══════════════════════════════════════════════════════════ */
.learn-tabs {
  display: flex;
  border-bottom: 1px solid rgba(55, 65, 81, 0.4);
  background: rgba(0, 0, 0, 0.15);
}

.learn-tab-btn {
  flex: 1;
  padding: 10px 16px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  background: transparent;
  border-bottom: 2px solid transparent;
}

.learn-tab-active {
  color: #60a5fa;
  border-bottom-color: #3b82f6;
  background: rgba(59, 130, 246, 0.06);
}

.learn-tab-inactive {
  color: #64748b;
}

.learn-tab-inactive:hover {
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.02);
}

.learn-tab-content {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

/* ══════════════════════════════════════════════════════════
   Code Viewer 仿终端窗口
   ══════════════════════════════════════════════════════════ */
.learn-code-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  margin: 12px;
  border-radius: 10px;
  border: 1px solid rgba(55, 65, 81, 0.5);
  overflow: hidden;
  background: #050505;
}

.learn-code-titlebar {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: rgba(30, 30, 30, 0.9);
  border-bottom: 1px solid rgba(55, 65, 81, 0.4);
}

.learn-code-loading {
  padding: 16px;
}

.learn-code-pre {
  flex: 1;
  margin: 0;
  padding: 16px;
  background: #050505;
  color: #4ade80;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
  line-height: 1.6;
  overflow: auto;
  white-space: pre;
  tab-size: 2;
}

.learn-code-pre code {
  font-family: inherit;
  color: inherit;
}

.learn-skeleton-line {
  height: 8px;
  border-radius: 4px;
  background: linear-gradient(90deg, rgba(100, 116, 139, 0.12), rgba(100, 116, 139, 0.06), rgba(100, 116, 139, 0.12));
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
  margin-bottom: 6px;
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* slide-right 过渡动画 */
.slide-right-enter-active {
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.slide-right-leave-active {
  transition: transform 0.25s cubic-bezier(0.4, 0, 1, 1);
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
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

.arch-flow :deep(.vue-flow__node) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  transition: transform 0.3s ease, filter 0.3s ease;
  cursor: pointer;
}

.arch-flow :deep(.vue-flow__node:hover) {
  transform: scale(1.05);
  z-index: 1000 !important;
  filter: brightness(1.2);
}

.arch-flow :deep(.vue-flow__node-group) {
  padding: 0 !important;
  border-radius: 8px !important;
  border-width: 1px !important;
  overflow: visible !important;
  pointer-events: none;
  transition: none;
}

.arch-flow :deep(.vue-flow__node-domain-group) {
  padding: 0 !important;
  border-radius: 12px !important;
  border: 1px dashed #3b82f6 !important;
  background: rgba(30, 58, 138, 0.1) !important;
  overflow: visible !important;
}

.arch-flow :deep(.vue-flow__node-default) {
  padding: 0 !important;
  border-radius: 6px !important;
  border-width: 1px !important;
  background: transparent !important;
}

.arch-flow :deep(.vue-flow__edge-textbg) {
  rx: 3;
  ry: 3;
}

.arch-flow :deep(.vue-flow__minimap) {
  border-radius: 8px;
  overflow: hidden;
}

.arch-flow :deep(.vue-flow__controls) {
  border-radius: 8px;
  overflow: hidden;
}

.arch-flow :deep(.vue-flow__controls-button) {
  background: #0a0a0a;
  border-color: #1e293b;
  fill: #64748b;
}

.arch-flow :deep(.vue-flow__controls-button:hover) {
  background: #1e293b;
  fill: #a78bfa;
}

.arch-group-node {
  width: 100%;
  height: 100%;
  border-width: 1px;
  border-style: solid;
  border-radius: 8px;
  overflow: hidden;
}

.arch-group-header {
  padding: 6px 10px;
  border-bottom-width: 1px;
  border-bottom-style: solid;
  display: flex;
  align-items: center;
  background: rgba(0, 0, 0, 0.3);
}

/* ══════════════════════════════════════════════════════════
   DDD 领域聚合结界 Group 节点样式
   ══════════════════════════════════════════════════════════ */
.arch-domain-group-node {
  width: 100%;
  height: 100%;
  border-radius: 12px;
  position: relative;
  pointer-events: none;
}

.arch-domain-group-label {
  position: absolute;
  top: 8px;
  right: 12px;
  padding: 2px 8px;
  background: rgba(30, 58, 138, 0.3);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 4px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  letter-spacing: 0.05em;
  pointer-events: auto;
  cursor: pointer;
}

.arch-domain-collapsed {
  cursor: pointer !important;
  pointer-events: auto !important;
}

.arch-domain-label-collapsed {
  top: 50%;
  right: 50%;
  transform: translate(50%, -50%);
  background: rgba(30, 58, 138, 0.5);
  border-color: rgba(59, 130, 246, 0.6);
  white-space: nowrap;
}

.arch-domain-collapsed-hint {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 8px;
  color: rgba(96, 165, 250, 0.5);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  pointer-events: none;
}

.arch-default-node {
  display: flex;
  align-items: center;
  padding: 6px 10px;
  border-width: 1px;
  border-style: solid;
  border-radius: 6px;
  white-space: nowrap;
  overflow: hidden;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.arch-default-node:hover {
  filter: brightness(1.2);
}

/* ══════════════════════════════════════════════════════════
   Diff Mode: 变更影响分析视觉样式
   ══════════════════════════════════════════════════════════ */

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

/* Diff Mode 边 SVG 样式 */
.arch-flow :deep(.vue-flow__edge.diff-edge-added .vue-flow__edge-path) {
  stroke: #22c55e !important;
  stroke-width: 2.5px !important;
  filter: drop-shadow(0 0 6px rgba(34, 197, 94, 0.5));
}
.arch-flow :deep(.vue-flow__edge.diff-edge-modified .vue-flow__edge-path) {
  stroke: #facc15 !important;
  stroke-width: 2.5px !important;
  filter: drop-shadow(0 0 6px rgba(250, 204, 21, 0.5));
}
.arch-flow :deep(.vue-flow__edge.diff-edge-impacted .vue-flow__edge-path) {
  stroke: #f97316 !important;
  stroke-width: 2px !important;
  stroke-dasharray: 6 3 !important;
  filter: drop-shadow(0 0 4px rgba(249, 115, 22, 0.4));
}
.arch-flow :deep(.vue-flow__edge.diff-edge-deleted .vue-flow__edge-path) {
  stroke: #ef4444 !important;
  stroke-width: 1.5px !important;
  stroke-dasharray: 4 4 !important;
  opacity: 0.5;
}
.arch-flow :deep(.vue-flow__edge.diff-edge-unchanged .vue-flow__edge-path) {
  stroke: #334155 !important;
  stroke-width: 1px !important;
  opacity: 0.15;
}

/* ══════════════════════════════════════════════════════════
   Path Finder 寻路高亮样式
   ══════════════════════════════════════════════════════════ */
.arch-flow :deep(.vue-flow__node.path-dimmed) {
  opacity: 0.15 !important;
  filter: grayscale(100%) !important;
  pointer-events: none;
}
.arch-flow :deep(.vue-flow__node.path-node-active) {
  z-index: 100 !important;
  filter: brightness(1.3) !important;
}
.arch-flow :deep(.vue-flow__node.path-endpoint) {
  z-index: 200 !important;
  filter: brightness(1.5) !important;
  box-shadow: 0 0 20px rgba(239, 68, 68, 0.6) !important;
}
.arch-flow :deep(.vue-flow__edge.path-edge-glow .vue-flow__edge-path) {
  stroke: #ef4444 !important;
  stroke-width: 3px !important;
  filter: drop-shadow(0 0 6px rgba(239, 68, 68, 0.5));
}
.arch-flow :deep(.vue-flow__edge.path-edge-dimmed .vue-flow__edge-path) {
  opacity: 0.15 !important;
}

.panel-slide-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.panel-slide-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}
.arch-slide-enter-from {
  opacity: 0;
}
.arch-slide-enter-from > :nth-child(2) {
  transform: scale(0.95);
  opacity: 0;
}
.arch-slide-leave-to {
  opacity: 0;
}
.arch-slide-leave-to > :nth-child(2) {
  transform: scale(0.95);
  opacity: 0;
}
.arch-slide-enter-active > :nth-child(2) {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.arch-slide-leave-active > :nth-child(2) {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}
</style>
