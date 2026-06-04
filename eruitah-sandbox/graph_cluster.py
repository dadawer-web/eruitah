"""
Eruitah 智能编程沙盒 - 图论社区发现 (Domain Clustering)

解决大型项目架构图的"毛线球"效应:
  使用 networkx 的社区发现算法，将联系紧密的节点聚合成"业务领域 (Domain)"，
  让前端可以按领域折叠/展开，大幅降低视觉复杂度。

核心算法:
  ┌──────────────────────────────────────────────────────────────────┐
  │  输入: nodes (节点列表), edges (边列表)                          │
  │                                                                  │
  │  1. 构建 networkx 无向图 (只看紧密程度，不关心方向)               │
  │  2. greedy_modularity_communities() 贪心模块度社区发现            │
  │  3. 为每个社区分配 cluster_id (domain_1, domain_2, ...)          │
  │  4. 将 cluster_id 追加到对应 node 字典中                         │
  │                                                                  │
  │  输出: 附加了 cluster_id 的 nodes 列表                           │
  └──────────────────────────────────────────────────────────────────┘
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 尝试导入 networkx，如果不可用则降级
try:
    import networkx as nx
    _HAS_NETWORKX = True
except ImportError:
    _HAS_NETWORKX = False
    logger.warning("networkx 未安装，社区发现功能不可用。安装: pip install networkx")


# 领域命名模板
DOMAIN_NAMES = [
    "核心业务", "用户体系", "数据访问", "接口网关", "基础设施",
    "认证授权", "消息通知", "配置管理", "日志监控", "缓存加速",
    "搜索引擎", "文件存储", "支付结算", "工作流引擎", "调度任务",
    "报表统计", "第三方集成", "测试验证", "文档生成", "安全防护",
]


def _generate_domain_name(cluster_idx: int, node_names: list[str]) -> str:
    """
    为社区生成一个有语义的领域名称。
    优先从节点名称中提取共同关键词，否则使用预设名称。
    """
    # 尝试从节点名称中提取共同后缀/前缀
    common_words = {}
    for name in node_names:
        parts = name.replace("_", " ").replace("-", " ").split()
        for part in parts:
            if len(part) > 2:  # 忽略太短的片段
                common_words[part.lower()] = common_words.get(part.lower(), 0) + 1

    # 找出现频率最高的词
    if common_words:
        sorted_words = sorted(common_words.items(), key=lambda x: -x[1])
        top_word, top_count = sorted_words[0]
        if top_count >= 2:  # 至少 2 个节点共享这个词
            return f"{top_word}领域"

    # 使用预设名称
    if cluster_idx < len(DOMAIN_NAMES):
        return DOMAIN_NAMES[cluster_idx]

    return f"领域_{cluster_idx + 1}"


def detect_domains(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """
    基于图论社区发现算法，将节点聚类为业务领域 (Domain)。

    Args:
        nodes: 节点列表，每个节点包含 id, type, name 等字段
        edges: 边列表，每条边包含 source, target, type 等字段

    Returns:
        附加了 cluster_id 和 cluster_name 的 nodes 列表
    """
    if not _HAS_NETWORKX:
        logger.debug("networkx 不可用，跳过社区发现")
        return nodes

    # 边界条件：节点太少，不值得聚类
    if len(nodes) < 3:
        logger.debug(f"节点数 {len(nodes)} < 3，跳过社区发现")
        for node in nodes:
            node["cluster_id"] = "domain_0"
            node["cluster_name"] = "全部"
        return nodes

    try:
        # 1. 构建 networkx 无向图
        G = nx.Graph()

        node_ids = set()
        for node in nodes:
            nid = node.get("id", "")
            if nid:
                G.add_node(nid)
                node_ids.add(nid)

        for edge in edges:
            source = edge.get("source", "")
            target = edge.get("target", "")
            if source in node_ids and target in node_ids:
                G.add_edge(source, target)

        # 边界条件：图没有边（全是孤立节点）
        if G.number_of_edges() == 0:
            logger.debug("图无连接边，跳过社区发现")
            for node in nodes:
                node["cluster_id"] = "domain_0"
                node["cluster_name"] = "孤立节点"
            return nodes

        # 2. 社区发现: 贪心模块度算法
        try:
            communities = nx.algorithms.community.greedy_modularity_communities(G)
        except Exception as e:
            logger.warning(f"贪心模块度社区发现失败，尝试连通分量降级: {e}")
            # 降级：用连通分量作为社区
            communities = list(nx.connected_components(G))

        if not communities:
            logger.debug("社区发现返回空结果，跳过")
            return nodes

        # 3. 为每个社区分配 cluster_id 和名称
        # 构建 node_id → cluster 映射
        node_cluster_map = {}
        cluster_info = []

        for idx, community in enumerate(sorted(communities, key=len, reverse=True)):
            cluster_id = f"domain_{idx}"
            # 收集社区内节点名称，用于生成语义名称
            community_names = []
            for nid in community:
                # 找到节点名称
                for node in nodes:
                    if node.get("id") == nid:
                        community_names.append(node.get("name", nid))
                        break

            cluster_name = _generate_domain_name(idx, community_names)
            cluster_info.append({
                "id": cluster_id,
                "name": cluster_name,
                "size": len(community),
            })

            for nid in community:
                node_cluster_map[nid] = {
                    "cluster_id": cluster_id,
                    "cluster_name": cluster_name,
                }

        # 4. 将 cluster_id 和 cluster_name 追加到节点
        for node in nodes:
            nid = node.get("id", "")
            if nid in node_cluster_map:
                node["cluster_id"] = node_cluster_map[nid]["cluster_id"]
                node["cluster_name"] = node_cluster_map[nid]["cluster_name"]
            else:
                # 孤立节点（没有边连接的）
                node["cluster_id"] = "domain_orphan"
                node["cluster_name"] = "孤立节点"

        domain_count = len(cluster_info)
        logger.info(
            f"🗺️ 图论社区发现完成: 自动识别出 {domain_count} 个高内聚业务领域 (Domain)"
        )
        for ci in cluster_info[:10]:
            logger.debug(f"  {ci['id']}: {ci['name']} ({ci['size']} 节点)")

        return nodes

    except Exception as e:
        logger.warning(f"社区发现算法异常，跳过聚类: {e}")
        return nodes
