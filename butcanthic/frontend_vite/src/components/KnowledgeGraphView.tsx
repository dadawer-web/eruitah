import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';

// ── 类型定义 ──

interface KGNode {
  id: string;
  category: string;
  sources?: string[];
}

interface KGEdge {
  source: string;
  target: string;
  relation: string;
}

interface GraphData {
  nodes: KGNode[];
  edges: KGEdge[];
  total_nodes: number;
  total_edges: number;
}

interface NodeDetail {
  id: string;
  category: string;
  sources: string[];
  neighbors: { id: string; relation: string; direction: string }[];
}

interface SearchResult {
  content: string;
  metadata: { source?: string; [k: string]: any };
  score: number;
  source: string;
  rerank_score?: number;
}

// ── 颜色映射 ──

const CATEGORY_COLORS: Record<string, string> = {
  '人': '#f472b6', '公司': '#60a5fa', '技术': '#34d399',
  '产品': '#fbbf24', '概念': '#a78bfa', '事件': '#fb923c',
  '组织': '#38bdf8', '地点': '#4ade80', 'entity': '#60a5fa',
  'concept': '#a78bfa', 'methodology': '#34d399', 'finding': '#fbbf24',
};

function getColor(category: string): string {
  return CATEGORY_COLORS[category] || '#818cf8';
}

// ── API 调用 ──

async function fetchGraphData(centerNode: string, userId: string): Promise<GraphData> {
  const params = new URLSearchParams({ depth: '2', max_nodes: '80' });
  if (centerNode) params.set('center_node', centerNode);
  const res = await fetch(`/api/v1/graph/data?${params}`, {
    headers: { 'X-User-Id': userId },
  });
  if (!res.ok) throw new Error(`Graph API error: ${res.status}`);
  return res.json();
}

async function fetchNodeDetail(nodeId: string, userId: string): Promise<NodeDetail> {
  const res = await fetch(`/api/v1/graph/node/${encodeURIComponent(nodeId)}`, {
    headers: { 'X-User-Id': userId },
  });
  if (!res.ok) throw new Error(`Node API error: ${res.status}`);
  return res.json();
}

async function fetchSearchResults(query: string, userId: string): Promise<SearchResult[]> {
  const res = await fetch('/api/v1/knowledge/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
    body: JSON.stringify({ query, top_k: 5 }),
  });
  if (!res.ok) throw new Error(`Search API error: ${res.status}`);
  const data = await res.json();
  return data.results || [];
}

// ── 主组件 ──

interface KnowledgeGraphViewProps {
  userId?: string;
  height?: number;
}

export function KnowledgeGraphView({ userId = '', height = 600 }: KnowledgeGraphViewProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'graph' | 'search'>('graph');
  const chartRef = useRef<any>(null);

  // 加载全图
  const loadFullGraph = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const data = await fetchGraphData('', userId);
      setGraphData(data);
    } catch (e) {
      console.error('Failed to load graph:', e);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  // 搜索图谱
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim() || !userId) return;
    setLoading(true);
    setSearchLoading(true);
    try {
      const [gData, sResults] = await Promise.all([
        fetchGraphData(searchQuery.trim(), userId),
        fetchSearchResults(searchQuery.trim(), userId),
      ]);
      setGraphData(gData);
      setSearchResults(sResults);
      setActiveTab('graph');
    } catch (e) {
      console.error('Search failed:', e);
    } finally {
      setLoading(false);
      setSearchLoading(false);
    }
  }, [searchQuery, userId]);

  // 节点点击
  const handleNodeClick = useCallback(async (nodeId: string) => {
    if (!userId) return;
    try {
      const detail = await fetchNodeDetail(nodeId, userId);
      setSelectedNode(detail);
    } catch (e) {
      console.error('Failed to load node detail:', e);
    }
  }, [userId]);

  // 初始加载
  useEffect(() => { loadFullGraph(); }, [loadFullGraph]);

  // ECharts 配置
  const chartOption = useMemo(() => {
    if (!graphData || graphData.nodes.length === 0) return null;

    const categories = Array.from(new Set(graphData.nodes.map(n => n.category)));
    const categoryMap = new Map(categories.map((c, i) => [c, i]));

    const nodes = graphData.nodes.map(node => {
      const degree = graphData.edges.filter(e => e.source === node.id || e.target === node.id).length;
      return {
        id: node.id,
        name: node.id,
        category: categoryMap.get(node.category) ?? 0,
        symbolSize: Math.max(24, Math.min(56, 24 + degree * 5)),
        itemStyle: {
          color: getColor(node.category),
          borderColor: '#1e1e2e',
          borderWidth: 2,
          shadowBlur: 8,
          shadowColor: getColor(node.category) + '50',
        },
        label: {
          show: true,
          fontSize: 10,
          fontWeight: 600,
          color: '#e0e0e0',
          fontFamily: 'system-ui, sans-serif',
          formatter: node.id.length > 10 ? node.id.slice(0, 10) + '…' : node.id,
        },
      };
    });

    const links = graphData.edges.map(edge => ({
      source: edge.source,
      target: edge.target,
      label: {
        show: true,
        fontSize: 8,
        color: '#666',
        formatter: edge.relation.length > 6 ? edge.relation.slice(0, 6) + '…' : edge.relation,
      },
      lineStyle: {
        color: '#3a3a5a',
        width: 1.2,
        curveness: 0.15,
        opacity: 0.6,
      },
    }));

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        backgroundColor: '#1a1a2eee',
        borderColor: '#333',
        textStyle: { color: '#e0e0e0', fontSize: 12 },
        formatter: (params: any) => {
          if (params.dataType === 'node') {
            const cat = categories[params.data.category] || '未知';
            return `<b>${params.name}</b><br/><span style="color:#888">类型：</span>${cat}`;
          }
          if (params.dataType === 'edge') {
            return `${params.data.source} → ${params.data.target}<br/><span style="color:#888">关系：</span>${params.data.label || ''}`;
          }
          return '';
        },
      },
      legend: {
        data: categories,
        textStyle: { color: '#aaa', fontSize: 10 },
        top: 4, left: 4, orient: 'horizontal',
        itemWidth: 10, itemHeight: 10, itemGap: 8,
      },
      series: [{
        type: 'graph',
        layout: 'force',
        data: nodes,
        links: links,
        categories: categories.map(c => ({ name: c, itemStyle: { color: getColor(c) } })),
        roam: true,
        draggable: true,
        force: {
          repulsion: 180,
          gravity: 0.06,
          edgeLength: [60, 180],
          layoutAnimation: true,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3, color: '#818cf8' },
          itemStyle: { shadowBlur: 20 },
          label: { fontSize: 13, fontWeight: 700 },
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 6],
        animationDuration: 600,
      }],
    };
  }, [graphData]);

  // ECharts 事件
  const onChartEvents = useMemo(() => ({
    click: (params: any) => {
      if (params.dataType === 'node') {
        handleNodeClick(params.name);
      }
    },
  }), [handleNodeClick]);

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100%', width: '100%',
      background: 'linear-gradient(135deg, #0a0a14 0%, #0f0f1a 50%, #12121f 100%)',
      color: '#e0e0e0', fontFamily: 'system-ui, -apple-system, sans-serif',
      overflow: 'hidden',
    }}>
      {/* ── 顶部搜索栏 ── */}
      <div style={{
        padding: '12px 16px',
        display: 'flex', gap: 8, alignItems: 'center',
        borderBottom: '1px solid rgba(129,140,248,0.12)',
        background: 'rgba(15,15,26,0.9)',
        backdropFilter: 'blur(12px)',
      }}>
        <div style={{ fontSize: 20 }}>🧠</div>
        <div style={{ flex: 1, position: 'relative' }}>
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="搜索概念、实体或关键词..."
            style={{
              width: '100%', padding: '10px 16px 10px 36px',
              background: 'rgba(30,30,50,0.8)',
              border: '1px solid rgba(129,140,248,0.2)',
              borderRadius: 10, color: '#e0e0e0', fontSize: 14,
              outline: 'none', transition: 'border-color 0.2s',
            }}
            onFocus={e => e.currentTarget.style.borderColor = 'rgba(129,140,248,0.5)'}
            onBlur={e => e.currentTarget.style.borderColor = 'rgba(129,140,248,0.2)'}
          />
          <span style={{
            position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)',
            color: '#666', fontSize: 14, pointerEvents: 'none',
          }}>🔍</span>
        </div>
        <button onClick={handleSearch} disabled={loading} style={{
          padding: '10px 20px', background: loading ? '#444' : '#6366f1',
          color: '#fff', border: 'none', borderRadius: 10, fontSize: 13,
          fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
          transition: 'background 0.2s',
        }}>
          {loading ? '搜索中...' : '搜索'}
        </button>
        <button onClick={loadFullGraph} style={{
          padding: '10px 14px', background: 'rgba(30,30,50,0.8)',
          color: '#aaa', border: '1px solid rgba(129,140,248,0.15)',
          borderRadius: 10, fontSize: 12, cursor: 'pointer',
        }}>
          全图
        </button>
      </div>

      {/* ── 统计条 ── */}
      {graphData && (
        <div style={{
          padding: '6px 16px', display: 'flex', gap: 16, alignItems: 'center',
          borderBottom: '1px solid rgba(129,140,248,0.08)',
          background: 'rgba(15,15,26,0.5)', fontSize: 11, color: '#666',
        }}>
          <span>📊 {graphData.nodes.length} 个实体</span>
          <span>🔗 {graphData.edges.length} 条关系</span>
          {graphData.total_nodes > graphData.nodes.length && (
            <span style={{ color: '#fbbf24' }}>（全图 {graphData.total_nodes} 节点，已截断）</span>
          )}
        </div>
      )}

      {/* ── 主内容区 ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* 左侧：图谱 / 搜索结果 */}
        <div style={{
          flex: selectedNode ? '0 0 70%' : '1',
          position: 'relative', overflow: 'hidden',
          transition: 'flex 0.3s ease',
        }}>
          {/* Tab 切换 */}
          <div style={{
            position: 'absolute', top: 8, right: 12, zIndex: 10,
            display: 'flex', gap: 4, background: 'rgba(15,15,26,0.85)',
            borderRadius: 8, padding: 3, border: '1px solid rgba(129,140,248,0.1)',
          }}>
            <button onClick={() => setActiveTab('graph')} style={{
              padding: '4px 12px', fontSize: 11, fontWeight: 600,
              background: activeTab === 'graph' ? '#6366f1' : 'transparent',
              color: activeTab === 'graph' ? '#fff' : '#888',
              border: 'none', borderRadius: 6, cursor: 'pointer',
            }}>图谱</button>
            <button onClick={() => setActiveTab('search')} style={{
              padding: '4px 12px', fontSize: 11, fontWeight: 600,
              background: activeTab === 'search' ? '#6366f1' : 'transparent',
              color: activeTab === 'search' ? '#fff' : '#888',
              border: 'none', borderRadius: 6, cursor: 'pointer',
            }}>
              搜索 {searchResults.length > 0 ? `(${searchResults.length})` : ''}
            </button>
          </div>

          {/* 图谱视图 */}
          {activeTab === 'graph' && (
            chartOption ? (
              <ReactECharts
                ref={chartRef}
                option={chartOption}
                onEvents={onChartEvents}
                style={{ height: '100%', width: '100%' }}
                opts={{ renderer: 'canvas' }}
                notMerge={true}
              />
            ) : (
              <div style={{
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                height: '100%', color: '#555', gap: 12,
              }}>
                <span style={{ fontSize: 48 }}>🕸️</span>
                <span style={{ fontSize: 14 }}>
                  {loading ? '正在加载图谱...' : '知识图谱为空，请先上传文档构建知识库'}
                </span>
              </div>
            )
          )}

          {/* 搜索结果视图 */}
          {activeTab === 'search' && (
            <div style={{
              padding: 16, overflowY: 'auto', height: '100%',
            }}>
              {searchLoading && <div style={{ color: '#888', textAlign: 'center', padding: 40 }}>搜索中...</div>}
              {!searchLoading && searchResults.length === 0 && (
                <div style={{ color: '#555', textAlign: 'center', padding: 40 }}>
                  输入关键词搜索知识库
                </div>
              )}
              {searchResults.map((result, idx) => (
                <div key={idx} style={{
                  background: 'rgba(30,30,50,0.6)',
                  border: '1px solid rgba(129,140,248,0.1)',
                  borderRadius: 10, padding: 14, marginBottom: 10,
                }}>
                  <div style={{
                    display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', marginBottom: 8,
                  }}>
                    <span style={{
                      fontSize: 11, padding: '2px 8px', borderRadius: 4,
                      background: result.source === 'graph' ? '#34d39930' : '#6366f130',
                      color: result.source === 'graph' ? '#34d399' : '#818cf8',
                    }}>
                      {result.source === 'graph' ? '图谱' : result.source === 'dense' ? '向量' : result.source}
                    </span>
                    <span style={{ fontSize: 10, color: '#555' }}>
                      得分: {(result.rerank_score || result.score).toFixed(3)}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, lineHeight: 1.6, color: '#ccc' }}>
                    {result.content.length > 300 ? result.content.slice(0, 300) + '...' : result.content}
                  </div>
                  {result.metadata?.source && (
                    <div style={{ fontSize: 10, color: '#555', marginTop: 6 }}>
                      来源: {result.metadata.source}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 右侧：溯源抽屉 */}
        {selectedNode && (
          <div style={{
            flex: '0 0 30%', borderLeft: '1px solid rgba(129,140,248,0.12)',
            background: 'rgba(15,15,26,0.95)', overflowY: 'auto',
            display: 'flex', flexDirection: 'column',
            animation: 'slideIn 0.2s ease',
          }}>
            {/* 抽屉头部 */}
            <div style={{
              padding: '12px 16px', display: 'flex', alignItems: 'center',
              borderBottom: '1px solid rgba(129,140,248,0.1)',
            }}>
              <span style={{
                fontSize: 16, fontWeight: 700, color: getColor(selectedNode.category),
                flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {selectedNode.id}
              </span>
              <button onClick={() => setSelectedNode(null)} style={{
                background: 'none', border: 'none', color: '#666',
                fontSize: 18, cursor: 'pointer', padding: 4,
              }}>✕</button>
            </div>

            {/* 节点属性 */}
            <div style={{ padding: '12px 16px' }}>
              <div style={{
                display: 'inline-block', padding: '3px 10px', borderRadius: 6,
                background: getColor(selectedNode.category) + '20',
                color: getColor(selectedNode.category),
                fontSize: 11, fontWeight: 600, marginBottom: 12,
              }}>
                {selectedNode.category}
              </div>

              {/* 来源文档 */}
              {selectedNode.sources && selectedNode.sources.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 11, color: '#666', marginBottom: 6, fontWeight: 600 }}>
                    📄 来源文档
                  </div>
                  {selectedNode.sources.map((src, i) => (
                    <div key={i} style={{
                      padding: '6px 10px', marginBottom: 4,
                      background: 'rgba(30,30,50,0.6)',
                      borderRadius: 6, fontSize: 12, color: '#aaa',
                      display: 'flex', alignItems: 'center', gap: 6,
                    }}>
                      <span>📎</span>
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {src}
                      </span>
                      <button
                        onClick={() => {
                          // 通知宿主页面打开原文档
                          window.parent.postMessage({
                            type: 'OPEN_SOURCE_DOCUMENT',
                            source: src,
                            nodeId: selectedNode.id,
                          }, '*');
                        }}
                        style={{
                          padding: '2px 8px', fontSize: 10,
                          background: '#6366f1', color: '#fff',
                          border: 'none', borderRadius: 4, cursor: 'pointer',
                          whiteSpace: 'nowrap', fontWeight: 600,
                        }}
                      >
                        查看原文档
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* 相邻关系 */}
              <div>
                <div style={{ fontSize: 11, color: '#666', marginBottom: 6, fontWeight: 600 }}>
                  🔗 关联实体 ({selectedNode.neighbors.length})
                </div>
                {selectedNode.neighbors.slice(0, 20).map((neighbor, i) => (
                  <div
                    key={i}
                    onClick={() => handleNodeClick(neighbor.id)}
                    style={{
                      padding: '5px 10px', marginBottom: 3,
                      background: 'rgba(30,30,50,0.4)',
                      borderRadius: 5, fontSize: 12, color: '#bbb',
                      cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
                      transition: 'background 0.15s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'rgba(99,102,241,0.15)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'rgba(30,30,50,0.4)'}
                  >
                    <span style={{ color: neighbor.direction === 'in' ? '#34d399' : '#60a5fa', fontSize: 10 }}>
                      {neighbor.direction === 'in' ? '←' : '→'}
                    </span>
                    <span style={{ flex: 1 }}>{neighbor.id}</span>
                    <span style={{ fontSize: 9, color: '#555' }}>{neighbor.relation}</span>
                  </div>
                ))}
                {selectedNode.neighbors.length > 20 && (
                  <div style={{ fontSize: 10, color: '#555', textAlign: 'center', padding: 4 }}>
                    ...还有 {selectedNode.neighbors.length - 20} 个关联实体
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* CSS 动画 */}
      <style>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(20px); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}

// ── 命令式挂载 ──

export function initKnowledgeGraphView(containerId: string, userId?: string) {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`KnowledgeGraphView: container #${containerId} not found`);
    return;
  }
  container.style.height = '100%';
  container.style.width = '100%';
  container.style.overflow = 'hidden';

  const root = createRoot(container);
  root.render(React.createElement(KnowledgeGraphView, { userId: userId || '' }));

  console.log('🧠 KnowledgeGraphView mounted on #' + containerId);
  return root;
}

(window as any).KnowledgeGraphView = KnowledgeGraphView;
(window as any).initKnowledgeGraphView = initKnowledgeGraphView;
