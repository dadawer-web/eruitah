import ELK from 'elkjs/lib/elk.bundled.js'

const elk = new ELK()

const DEFAULT_NODE_WIDTH = 180
const DEFAULT_NODE_HEIGHT = 50

const ELK_LAYOUT_OPTIONS = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.layered.spacing.nodeNodeBetweenLayers': '100',
  'elk.spacing.nodeNode': '60',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
  'elk.layered.compaction.postCompaction.strategy': 'LEFT',
  'elk.padding': '[top=30,left=20,right=20,bottom=20]',
}

function repairInput(children, edges) {
  const validIds = new Set()
  const walk = (nodes) => {
    for (const c of nodes) {
      validIds.add(c.id)
      if (c.children) walk(c.children)
    }
  }
  walk(children)

  const repairedChildren = children.map((c) => ({
    ...c,
    width: c.width || DEFAULT_NODE_WIDTH,
    height: c.height || DEFAULT_NODE_HEIGHT,
  }))

  const repairedEdges = edges.filter(
    (e) =>
      e.sources.every((s) => validIds.has(s)) &&
      e.targets.every((t) => validIds.has(t))
  )

  return { children: repairedChildren, edges: repairedEdges }
}

export async function getLayoutedElements(nodes, edges, options = {}) {
  if (!nodes || nodes.length === 0) {
    return { nodes: [], edges: edges || [] }
  }

  const layoutOptions = { ...ELK_LAYOUT_OPTIONS, ...options }

  const elkChildren = nodes.map((node) => ({
    id: node.id,
    width: node.dimensions?.width || node.style?.width
      ? parseInt(String(node.style.width), 10) || DEFAULT_NODE_WIDTH
      : DEFAULT_NODE_WIDTH,
    height: node.dimensions?.height || node.style?.height
      ? parseInt(String(node.style.height), 10) || DEFAULT_NODE_HEIGHT
      : DEFAULT_NODE_HEIGHT,
  }))

  const elkEdges = (edges || [])
    .filter((e) => e.source && e.target)
    .map((e, i) => ({
      id: e.id || `e-${e.source}-${e.target}-${i}`,
      sources: [e.source],
      targets: [e.target],
    }))

  const { children: repairedChildren, edges: repairedEdges } = repairInput(
    elkChildren,
    elkEdges
  )

  const elkInput = {
    id: 'root',
    layoutOptions,
    children: repairedChildren,
    edges: repairedEdges,
  }

  try {
    const positioned = await elk.layout(elkInput)

    const posMap = new Map()
    for (const child of positioned.children || []) {
      posMap.set(child.id, {
        x: child.x ?? 0,
        y: child.y ?? 0,
      })
    }

    const layoutedNodes = nodes.map((node) => {
      const pos = posMap.get(node.id) || { x: 0, y: 0 }
      return {
        ...node,
        position: { x: pos.x, y: pos.y },
      }
    })

    return { nodes: layoutedNodes, edges: edges || [] }
  } catch (err) {
    console.error('[elkLayout] ELK layout failed:', err)
    const fallbackNodes = nodes.map((node, i) => ({
      ...node,
      position: node.position || { x: i * 250, y: 0 },
    }))
    return { nodes: fallbackNodes, edges: edges || [] }
  }
}

export { ELK_LAYOUT_OPTIONS, DEFAULT_NODE_WIDTH, DEFAULT_NODE_HEIGHT }
