<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { VueFlow, useVueFlow, Position, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import ELK from 'elkjs/lib/elk.bundled.js'

const props = defineProps({
  visible: Boolean,
  graphData: {
    type: Object,
    default: () => ({ nodes: [], edges: [] })
  }
})
const emit = defineEmits(['close', 'nodeClick'])

const loading = ref(false)
const error = ref(null)
const flowNodes = ref([])
const flowEdges = ref([])
const selectedNode = ref(null)
const searchQuery = ref('')
const elkInstance = new ELK()

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
  return TYPE_CONFIG[type] || TYPE_CONFIG.function
}

function groupNodesByFile(nodes) {
  const groups = new Map()
  const orphans = []

  for (const node of nodes) {
    const parent = extractParentNodeId(node)
    if (parent) {
      if (!groups.has(parent)) groups.set(parent, [])
      groups.get(parent).push(node)
    } else if (node.type === 'file') {
      if (!groups.has(node.id)) groups.set(node.id, [])
      groups.get(node.id).unshift(node)
    } else {
      orphans.push(node)
    }
  }

  return { groups, orphans }
}

function extractParentNodeId(node) {
  const parts = node.id.split(':')
  if (parts.length >= 3 && (node.type === 'function' || node.type === 'class')) {
    return 'file:' + parts[1]
  }
  return null
}

async function computeElkLayout(rawNodes, rawEdges) {
  if (!rawNodes.length) return { nodes: [], edges: [] }

  const { groups, orphans } = groupNodesByFile(rawNodes)

  const elkChildren = []
  const elkEdges = []
  const nodeDimMap = new Map()

  for (const [groupId, groupNodes] of groups) {
    const fileNode = groupNodes.find(n => n.type === 'file')
    const childNodes = groupNodes.filter(n => n.type !== 'file')

    if (childNodes.length === 0 && fileNode) {
      const w = 200
      const h = 44
      nodeDimMap.set(fileNode.id, { width: w, height: h })
      elkChildren.push({ id: fileNode.id, width: w, height: h })
      continue
    }

    const innerChildren = []
    for (const cn of childNodes) {
      const labelLen = (cn.name || cn.id).length
      const w = Math.max(160, Math.min(280, labelLen * 8 + 40))
      const h = cn.type === 'class' ? 48 : 40
      nodeDimMap.set(cn.id, { width: w, height: h })
      innerChildren.push({ id: cn.id, width: w, height: h })
    }

    const containerW = Math.max(260, ...innerChildren.map(c => c.width)) + 40
    const containerH = innerChildren.reduce((s, c) => s + c.height, 0) + innerChildren.length * 8 + 56

    if (fileNode) {
      nodeDimMap.set(fileNode.id, { width: containerW, height: containerH })
      elkChildren.push({
        id: fileNode.id,
        width: containerW,
        height: containerH,
        children: innerChildren,
        layoutOptions: {
          'elk.padding': '[top=36,left=12,right=12,bottom=12]',
          'elk.spacing.nodeNode': '8',
        }
      })
    }
  }

  for (const orphan of orphans) {
    const labelLen = (orphan.name || orphan.id).length
    const w = Math.max(160, Math.min(280, labelLen * 8 + 40))
    const h = orphan.type === 'class' ? 48 : 40
    nodeDimMap.set(orphan.id, { width: w, height: h })
    elkChildren.push({ id: orphan.id, width: w, height: h })
  }

  const validIds = new Set(rawNodes.map(n => n.id))
  for (const edge of rawEdges) {
    if (validIds.has(edge.source) && validIds.has(edge.target)) {
      elkEdges.push({
        id: `e-${edge.source}-${edge.target}`,
        sources: [edge.source],
        targets: [edge.target],
      })
    }
  }

  const elkInput = {
    id: 'root',
    layoutOptions: {
      'algorithm': 'layered',
      'elk.direction': 'DOWN',
      'elk.layered.spacing.nodeNodeBetweenLayers': '100',
      'elk.spacing.nodeNode': '50',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.compaction.postCompaction.strategy': 'LEFT',
      'elk.padding': '[top=30,left=20,right=20,bottom=20]',
      'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
    },
    children: elkChildren,
    edges: elkEdges,
  }

  try {
    const positioned = await elkInstance.layout(elkInput)

    const posMap = new Map()
    function collectPositions(elkNode, offsetX = 0, offsetY = 0) {
      if (elkNode.children) {
        for (const child of elkNode.children) {
          const cx = offsetX + (child.x || 0)
          const cy = offsetY + (child.y || 0)
          posMap.set(child.id, { x: cx, y: cy })
          if (child.children) {
            collectPositions(child, cx, cy)
          }
        }
      }
    }
    collectPositions(positioned)

    for (const child of positioned.children || []) {
      posMap.set(child.id, { x: child.x || 0, y: child.y || 0 })
    }

    const vfNodes = rawNodes.map(node => {
      const pos = posMap.get(node.id) || { x: 0, y: 0 }
      const dims = nodeDimMap.get(node.id) || { width: 200, height: 44 }
      const cfg = getTypeConfig(node.type)
      const isFile = node.type === 'file'
      const hasChildren = isFile && groups.has(node.id) && groups.get(node.id).some(n => n.type !== 'file')

      return {
        id: node.id,
        type: hasChildren ? 'group' : undefined,
        position: { x: pos.x, y: pos.y },
        data: {
          label: node.name || node.id,
          nodeType: node.type,
          color: cfg.color,
          bg: cfg.bg,
          icon: cfg.icon,
          file: node.file || '',
          extra: node,
        },
        style: {
          width: dims.width + 'px',
          height: dims.height + 'px',
        },
        sourcePosition: Position.BOTTOM,
        targetPosition: Position.TOP,
      }
    })

    const vfEdges = rawEdges
      .filter(e => validIds.has(e.source) && validIds.has(e.target))
      .map((edge, i) => {
        const style = EDGE_STYLE[edge.type] || EDGE_STYLE.contains
        return {
          id: `e${i}-${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          type: 'smoothstep',
          animated: edge.type === 'calls',
          style: {
            stroke: style.color,
            strokeWidth: style.width,
            strokeDasharray: style.style === 'dashed' ? '5 5' : undefined,
          },
          label: edge.type !== 'contains' ? edge.type : undefined,
          labelStyle: { fill: style.color, fontSize: '9px', fontWeight: 600 },
          labelBgStyle: { fill: '#0a0a0a', stroke: style.color, strokeWidth: 0.5, fillOpacity: 0.9 },
          labelBgPadding: [4, 6],
          labelBgBorderRadius: 3,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: style.color,
            width: 12,
            height: 12,
          },
        }
      })

    return { nodes: vfNodes, edges: vfEdges }
  } catch (err) {
    console.error('ELK layout failed:', err)
    error.value = `布局计算失败: ${err.message}`
    return { nodes: [], edges: [] }
  }
}

async function processGraph() {
  if (!props.graphData?.nodes?.length) return

  loading.value = true
  error.value = null

  try {
    const result = await computeElkLayout(props.graphData.nodes, props.graphData.edges)
    flowNodes.value = result.nodes
    flowEdges.value = result.edges
  } finally {
    loading.value = false
  }
}

watch(() => props.graphData, () => {
  if (props.visible) processGraph()
}, { deep: true })

watch(() => props.visible, (v) => {
  if (v && props.graphData?.nodes?.length) {
    nextTick(() => processGraph())
  }
})

onMounted(() => {
  if (props.visible && props.graphData?.nodes?.length) {
    processGraph()
  }
})

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
  if (!searchQuery.value) return flowNodes.value
  const q = searchQuery.value.toLowerCase()
  return flowNodes.value.filter(n => {
    const label = (n.data?.label || '').toLowerCase()
    const nodeType = (n.data?.nodeType || '').toLowerCase()
    return label.includes(q) || nodeType.includes(q)
  })
})

const filteredNodeIds = computed(() => new Set(filteredNodes.value.map(n => n.id)))

const displayEdges = computed(() => {
  const ids = filteredNodeIds.value
  return flowEdges.value.filter(e => ids.has(e.source) && ids.has(e.target))
})

function handleNodeClick(event) {
  selectedNode.value = event.node?.data?.extra || null
  emit('nodeClick', event.node?.data?.extra)
}

function handlePaneClick() {
  selectedNode.value = null
}
</script>

<template>
  <Transition name="arch-slide">
    <div v-if="visible" class="fixed inset-0 z-[100] flex justify-end" @click.self="emit('close')">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>

      <div class="relative w-[900px] max-w-[95vw] h-full bg-geek-surface border-l border-cyan-500/20 shadow-[0_0_40px_rgba(0,255,136,0.06)] flex flex-col">

        <div class="flex items-center justify-between px-5 py-3 border-b border-geek-border shrink-0 bg-geek-bg/50">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-violet-900/40 border border-violet-500/30 flex items-center justify-center text-sm">🏗️</div>
            <div>
              <div class="text-sm font-bold text-violet-400">Architecture Viewer</div>
              <div class="text-[10px] text-geek-text-dim">ELK 正交布局 · 跨文件依赖分析</div>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <div class="relative">
              <input
                v-model="searchQuery"
                placeholder="搜索节点..."
                class="w-40 px-2.5 py-1 text-[11px] bg-geek-bg border border-geek-border rounded text-geek-text placeholder-geek-text-dim focus:outline-none focus:border-violet-500/50"
              />
              <span class="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-geek-text-dim">⌘</span>
            </div>
            <button @click="emit('close')" class="text-geek-text-dim hover:text-geek-text text-lg leading-none ml-2">×</button>
          </div>
        </div>

        <div class="flex-1 min-h-0 relative bg-[#080c14]">
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
            v-if="flowNodes.length"
            :nodes="filteredNodes"
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
              <div
                class="arch-group-node"
                :style="{
                  borderColor: groupNodeProps.data?.color + '40',
                  background: 'linear-gradient(135deg, ' + groupNodeProps.data?.bg + 'cc, ' + groupNodeProps.data?.bg + '66)',
                }"
              >
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
                }"
              >
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
          </div>
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
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.arch-flow :deep(.vue-flow__node) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.arch-flow :deep(.vue-flow__node-group) {
  padding: 0 !important;
  border-radius: 8px !important;
  border-width: 1px !important;
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
  transform: translateX(100%);
}
.arch-slide-leave-to {
  opacity: 0;
}
.arch-slide-leave-to > :nth-child(2) {
  transform: translateX(100%);
}
.arch-slide-enter-active > :nth-child(2) {
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.arch-slide-leave-active > :nth-child(2) {
  transition: transform 0.25s cubic-bezier(0.4, 0, 1, 1);
}
</style>
