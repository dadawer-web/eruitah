import React, { useMemo, useEffect, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';

export interface KGNode {
  id: string;
  category: string;
}

export interface KGEdge {
  source: string;
  target: string;
  label: string;
}

export interface KnowledgeGraphData {
  nodes: KGNode[];
  edges: KGEdge[];
}

const CATEGORY_COLORS: Record<string, string> = {
  '人': '#f472b6',
  '公司': '#60a5fa',
  '技术': '#34d399',
  '产品': '#fbbf24',
  '概念': '#a78bfa',
  '事件': '#fb923c',
  '组织': '#38bdf8',
  '地点': '#4ade80',
};

const DEFAULT_COLOR = '#818cf8';

function getCategoryColor(category: string): string {
  return CATEGORY_COLORS[category] || DEFAULT_COLOR;
}

interface KnowledgeGraphProps {
  data: KnowledgeGraphData;
  height?: number;
}

export function KnowledgeGraph({ data, height = 500 }: KnowledgeGraphProps) {
  const option = useMemo(() => {
    const categories = Array.from(new Set(data.nodes.map(n => n.category)));
    const categoryMap = new Map(categories.map((c, i) => [c, i]));

    const echartsCategories = categories.map(c => ({
      name: c,
      itemStyle: { color: getCategoryColor(c) },
    }));

    const nodes = data.nodes.map(node => ({
      id: node.id,
      name: node.id,
      category: categoryMap.get(node.category) ?? 0,
      symbolSize: Math.max(28, Math.min(50, 28 + data.edges.filter(e => e.source === node.id || e.target === node.id).length * 6)),
      itemStyle: {
        color: getCategoryColor(node.category),
        borderColor: '#1e1e2e',
        borderWidth: 2,
        shadowBlur: 10,
        shadowColor: getCategoryColor(node.category) + '60',
      },
      label: {
        show: true,
        fontSize: 11,
        fontWeight: 600,
        color: '#e0e0e0',
        fontFamily: 'system-ui, sans-serif',
      },
    }));

    const links = data.edges.map(edge => ({
      source: edge.source,
      target: edge.target,
      label: {
        show: true,
        fontSize: 9,
        color: '#888',
        formatter: edge.label.length > 8 ? edge.label.slice(0, 8) + '…' : edge.label,
        fontFamily: 'system-ui, sans-serif',
      },
      lineStyle: {
        color: '#444',
        width: 1.5,
        curveness: 0.15,
        opacity: 0.7,
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
        textStyle: { color: '#aaa', fontSize: 11 },
        top: 8,
        left: 8,
        orient: 'horizontal',
        itemWidth: 12,
        itemHeight: 12,
        itemGap: 12,
      },
      series: [{
        type: 'graph',
        layout: 'force',
        data: nodes,
        links: links,
        categories: echartsCategories,
        roam: true,
        draggable: true,
        force: {
          repulsion: 200,
          gravity: 0.08,
          edgeLength: [80, 200],
          layoutAnimation: true,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3, color: '#818cf8' },
          itemStyle: { shadowBlur: 20 },
          label: { fontSize: 14, fontWeight: 700 },
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 8],
        animationDuration: 800,
        animationEasingUpdate: 'quinticInOut',
      }],
    };
  }, [data]);

  return (
    <div style={{
      background: 'linear-gradient(135deg, #0f0f1a 0%, #161625 100%)',
      borderRadius: 12,
      border: '1px solid rgba(129, 140, 248, 0.15)',
      padding: 16,
      position: 'relative',
      overflow: 'hidden',
      height: `${height + 60}px`,
      width: '100%',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 8,
      }}>
        <span style={{ fontSize: 18 }}>🧠</span>
        <span style={{
          fontSize: 14,
          fontWeight: 700,
          color: '#a78bfa',
          letterSpacing: 0.5,
        }}>AI 知识图谱已生成</span>
        <span style={{
          fontSize: 11,
          color: '#666',
          marginLeft: 'auto',
        }}>{data.nodes.length} 个实体 · {data.edges.length} 条关系</span>
      </div>
      <ReactECharts
        option={option}
        style={{ height: `${height}px`, width: '100%' }}
        opts={{ renderer: 'canvas' }}
        notMerge={true}
      />
    </div>
  );
}

export function initKnowledgeGraph(containerId: string, data: KnowledgeGraphData) {
  const container = document.getElementById(containerId);
  if (!container) {
    console.error(`KnowledgeGraph: container #${containerId} not found`);
    return;
  }
  container.style.height = '560px';
  container.style.width = '100%';
  container.style.overflow = 'hidden';

  const chartInstance = echarts.init(container, undefined, { renderer: 'canvas' });

  const categories = Array.from(new Set(data.nodes.map(n => n.category)));
  const categoryMap = new Map(categories.map((c, i) => [c, i]));
  const echartsCategories = categories.map(c => ({
    name: c,
    itemStyle: { color: getCategoryColor(c) },
  }));

  const nodes = data.nodes.map(node => ({
    id: node.id,
    name: node.id,
    category: categoryMap.get(node.category) ?? 0,
    symbolSize: Math.max(28, Math.min(50, 28 + data.edges.filter(e => e.source === node.id || e.target === node.id).length * 6)),
    itemStyle: {
      color: getCategoryColor(node.category),
      borderColor: '#1e1e2e',
      borderWidth: 2,
      shadowBlur: 10,
      shadowColor: getCategoryColor(node.category) + '60',
    },
    label: {
      show: true,
      fontSize: 11,
      fontWeight: 600,
      color: '#e0e0e0',
      fontFamily: 'system-ui, sans-serif',
    },
  }));

  const links = data.edges.map(edge => ({
    source: edge.source,
    target: edge.target,
    label: {
      show: true,
      fontSize: 9,
      color: '#888',
      formatter: edge.label.length > 8 ? edge.label.slice(0, 8) + '…' : edge.label,
    },
    lineStyle: {
      color: '#444',
      width: 1.5,
      curveness: 0.15,
      opacity: 0.7,
    },
  }));

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: '#1a1a2eee',
      borderColor: '#333',
      textStyle: { color: '#e0e0e0', fontSize: 12 },
    },
    legend: {
      data: categories,
      textStyle: { color: '#aaa', fontSize: 11 },
      top: 8,
      left: 8,
    },
    series: [{
      type: 'graph',
      layout: 'force',
      data: nodes,
      links: links,
      categories: echartsCategories,
      roam: true,
      draggable: true,
      force: { repulsion: 200, gravity: 0.08, edgeLength: [80, 200], layoutAnimation: true },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3, color: '#818cf8' },
        label: { fontSize: 14, fontWeight: 700 },
      },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 8],
      animationDuration: 800,
    }],
  };

  chartInstance.setOption(option);

  const resizeHandler = () => chartInstance.resize();
  window.addEventListener('resize', resizeHandler);

  (container as any)._echartsInstance = chartInstance;
  (container as any)._resizeHandler = resizeHandler;

  console.log('🔥 KnowledgeGraph ECharts 渲染完成:', data.nodes.length, 'nodes,', data.edges.length, 'edges');

  return chartInstance;
}

(window as any).KnowledgeGraph = KnowledgeGraph;
(window as any).initKnowledgeGraph = initKnowledgeGraph;
