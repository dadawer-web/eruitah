import ELK from 'elkjs/lib/elk.bundled.js';

const elk = new ELK();

// ── 对标 Understand-Anything 的 ELK 配置 ──
const NODE_WIDTH = 280;
const NODE_HEIGHT = 120;

const ELK_DEFAULT_LAYOUT_OPTIONS = {
  'elk.algorithm': 'layered',
  'elk.direction': 'DOWN',
  'elk.layered.spacing.nodeNodeBetweenLayers': '80',
  'elk.spacing.nodeNode': '60',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.layered.compaction.postCompaction.strategy': 'LEFT',
  'elk.padding': '[top=40,left=20,right=20,bottom=20]',
};

// ── 业务流程图模式：直角流水线布局 ──
const ELK_FLOW_LAYOUT_OPTIONS = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.layered.spacing.nodeNodeBetweenLayers': '100',
  'elk.spacing.nodeNode': '50',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
  'elk.layered.alignment': 'CENTER',
  'elk.layered.compaction.postCompaction.strategy': 'LEFT',
  'elk.padding': '[top=40,left=30,right=30,bottom=20]',
};

/**
 * 对标 Understand-Anything 的扁平 ELK 布局
 *
 * UA 的核心思路：
 * - 所有节点（包括容器/Group）都作为扁平的顶层节点参与 ELK 布局
 * - Group 节点作为"不透明原子"（opaque atom），ELK 只算它的位置
 * - Group 的宽高由其子节点的包围盒决定
 * - 子节点在 Group 内部用第二阶段单独布局
 * - 边决定层级关系，ELK 根据 source→target 自动分层
 */
export const layoutGraph = async (nodes, edges, mode = 'structural') => {
  if (!nodes || nodes.length === 0) return [];

  // 根据模式选择布局配置
  const layoutOptions = mode === 'flow'
    ? ELK_FLOW_LAYOUT_OPTIONS
    : ELK_DEFAULT_LAYOUT_OPTIONS;

  // 1. 分离 Group 和普通节点
  const groupNodes = nodes.filter(n => n.type === 'group');
  const normalNodes = nodes.filter(n => n.type !== 'group');

  // 2. 构建扁平 ELK 输入（对标 UA 的 nodesToElkInput）
  //    所有节点都在顶层，Group 作为不透明原子
  const elkChildren = [];

  // 普通节点
  for (const n of normalNodes) {
    const styleWidth = n.style?.width ? parseInt(String(n.style.width), 10) : 0;
    const styleHeight = n.style?.height ? parseInt(String(n.style.height), 10) : 0;
    elkChildren.push({
      id: String(n.id),
      width: styleWidth > 0 ? styleWidth : NODE_WIDTH,
      height: styleHeight > 0 ? styleHeight : NODE_HEIGHT,
    });
  }

  // Group 节点：先给一个初始尺寸，布局后再根据子节点包围盒调整
  for (const g of groupNodes) {
    // 计算子节点数量来估算 Group 尺寸
    const childCount = normalNodes.filter(n => {
      const parentId = n.parentNode || n._domainGroup || n._fileGroup || (n.data && n.data.cluster_id);
      return String(parentId) === String(g.id);
    }).length;

    // 折叠状态：子节点被前端扣留，childCount === 0
    // 此时必须给默认宽高，防止结界塌缩
    if (childCount === 0 || g.data?.isCollapsed) {
      elkChildren.push({
        id: String(g.id),
        width: 280,
        height: 80,
      });
      continue;
    }

    const cols = Math.ceil(Math.sqrt(Math.max(childCount, 1)));
    const rows = Math.ceil(childCount / cols);
    const groupWidth = Math.max(320, cols * 280 + 80);
    const groupHeight = Math.max(180, rows * 120 + 100);

    elkChildren.push({
      id: String(g.id),
      width: groupWidth,
      height: groupHeight,
    });
  }

  // 3. 所有边都传给 ELK（包括跨组和组内的边）
  const allElkIds = new Set(elkChildren.map(c => c.id));
  const elkEdges = (edges || [])
    .filter(e => allElkIds.has(String(e.source)) && allElkIds.has(String(e.target)))
    .map((e, i) => ({
      id: String(e.id || `e-${e.source}-${e.target}-${i}`),
      sources: [String(e.source)],
      targets: [String(e.target)],
    }));

  const graph = {
    id: 'root',
    layoutOptions,
    children: elkChildren,
    edges: elkEdges,
  };

  try {
    const layoutedGraph = await elk.layout(graph);

    // 4. 提取 ELK 算好的坐标
    const positionMap = new Map();
    const sizeMap = new Map();

    if (layoutedGraph.children) {
      for (const c of layoutedGraph.children) {
        if (c.x !== undefined && c.y !== undefined) {
          positionMap.set(c.id, { x: c.x, y: c.y });
          sizeMap.set(c.id, { width: c.width, height: c.height });
        }
      }
    }

    // 5. 组装普通节点坐标
    const resultNodes = normalNodes.map(n => {
      const pos = positionMap.get(String(n.id));
      if (!pos) return n;
      return { ...n, position: { x: pos.x, y: pos.y } };
    });

    // 6. 组装 Group 节点：使用 ELK 算出的位置，但根据子节点包围盒调整大小
    for (const groupNode of groupNodes) {
      const groupPos = positionMap.get(String(groupNode.id));
      if (!groupPos) continue;

      // 折叠状态的 Group：直接使用 ELK 算出的位置 + 固定小尺寸
      if (groupNode.data?.isCollapsed) {
        resultNodes.push({
          ...groupNode,
          position: { x: groupPos.x, y: groupPos.y },
          style: {
            ...(groupNode.style || {}),
            width: '280px',
            height: '80px',
          },
        });
        continue;
      }

      // 找出属于这个 Group 的子节点
      const childNodes = normalNodes.filter(n => {
        const parentId = n.parentNode || n._domainGroup || n._fileGroup || (n.data && n.data.cluster_id);
        return String(parentId) === String(groupNode.id);
      });

      // 如果有子节点，根据子节点的实际位置计算包围盒
      if (childNodes.length > 0) {
        const childPositions = childNodes
          .map(n => positionMap.get(String(n.id)))
          .filter(p => p !== undefined);

        const childSizes = childNodes
          .map(n => sizeMap.get(String(n.id)))
          .filter(s => s !== undefined);

        if (childPositions.length > 0) {
          const padding = 40;
          const topPadding = 60;

          const minX = Math.min(...childPositions.map(p => p.x));
          const minY = Math.min(...childPositions.map(p => p.y));
          const maxX = Math.max(...childPositions.map((p, i) => {
            const s = childSizes[i] || { width: NODE_WIDTH };
            return p.x + s.width;
          }));
          const maxY = Math.max(...childPositions.map((p, i) => {
            const s = childSizes[i] || { height: NODE_HEIGHT };
            return p.y + s.height;
          }));

          resultNodes.push({
            ...groupNode,
            position: { x: minX - padding, y: minY - topPadding },
            style: {
              ...(groupNode.style || {}),
              width: `${maxX - minX + padding * 2}px`,
              height: `${maxY - minY + topPadding + padding}px`,
            },
          });
          continue;
        }
      }

      // 没有子节点或子节点没有位置，使用 ELK 算出的位置和估算大小
      const groupSize = sizeMap.get(String(groupNode.id));
      resultNodes.push({
        ...groupNode,
        position: { x: groupPos.x, y: groupPos.y },
        style: {
          ...(groupNode.style || {}),
          width: `${groupSize?.width || 320}px`,
          height: `${groupSize?.height || 180}px`,
        },
      });
    }

    return resultNodes;

  } catch (error) {
    console.error('ELK 排版引擎崩溃:', error);
    return nodes;
  }
};

// 兼容旧调用方
export async function getLayoutedElements(nodes, edges, options = {}) {
  if (!nodes || nodes.length === 0) return { nodes: [], edges: edges || [] }
  const mode = options.mode || 'structural'
  const resultNodes = await layoutGraph(nodes, edges, mode)
  return { nodes: resultNodes, edges: edges || [] }
}
