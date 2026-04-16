#!/usr/bin/env python3
"""
XMind to Neo4j 导入脚本
将408考研思维导图导入Neo4j图数据库
"""

from xmindparser import xmind_to_dict
from neo4j import GraphDatabase
import sys
import os

# Neo4j 数据库连接配置
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "12345678"

class XMindToNeo4j:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.node_count = 0
        self.relation_count = 0

    def close(self):
        self.driver.close()

    def clear_existing_data(self):
        """清空现有数据"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("已清空现有数据")

    def calculate_size(self, level):
        """根据知识点层级计算size值
        
        size越小，单次答题对掌握度的贡献越大（alpha = 1/size）
        - Level 0-1: 根节点/科目级 (size=10) - 极大概念
        - Level 2-3: 主要章节 (size=7-8) - 中大型概念
        - Level 4-5: 具体知识点 (size=4-6) - 中等概念
        - Level 6+: 细节考点 (size=2) - 小概念
        """
        if level <= 1:
            return 10
        elif level == 2:
            return 8
        elif level == 3:
            return 7
        elif level == 4:
            return 6
        elif level == 5:
            return 4
        else:
            return 2

    def create_root_node(self):
        """创建根节点"""
        with self.driver.session() as session:
            session.run("""
                MERGE (c:Concept {name: '408计算机学科专业基础'})
                ON CREATE SET c.level = 0, c.subject = 'ROOT', c.size = 10
            """)
            print("创建根节点: 408计算机学科专业基础")
            self.node_count += 1

    def process_xmind(self, file_path, subject_name):
        """处理单个XMind文件"""
        print(f"\n{'='*50}")
        print(f"正在解析文件: {file_path}")
        print(f"科目: {subject_name}")
        print(f"{'='*50}")
        
        data = xmind_to_dict(file_path)
        if not data:
            print(f"警告: 无法解析文件 {file_path}")
            return
        
        root_topic = data[0]['topic']
        root_name = root_topic.get('title', '').strip()
        
        with self.driver.session() as session:
            size = self.calculate_size(1)
            session.run("""
                MERGE (c:Concept {name: $name})
                ON CREATE SET c.level = 1, c.subject = $subject, c.size = $size
            """, name=root_name, subject=subject_name, size=size)
            print(f"创建科目节点: {root_name} (size={size})")
            self.node_count += 1
            
            # 连接到根节点
            session.run("""
                MATCH (root:Concept {name: '408计算机学科专业基础'})
                MATCH (subject:Concept {name: $subject_name})
                MERGE (subject)-[:BELONGS_TO]->(root)
            """, subject_name=root_name)
            self.relation_count += 1
            
            # 递归处理子节点
            if 'topics' in root_topic:
                for sub_topic in root_topic['topics']:
                    self._traverse_and_create(session, sub_topic, root_name, subject_name, level=2)
        
        print(f"✅ 文件 {file_path} 导入完成！")

    def _traverse_and_create(self, session, topic, parent_name, subject_name, level):
        """递归创建节点和关系"""
        current_name = topic.get('title', '').strip()
        if not current_name:
            return
        
        size = self.calculate_size(level)
        
        session.run("""
            MERGE (c:Concept {name: $name})
            ON CREATE SET c.level = $level, c.subject = $subject, c.size = $size
        """, name=current_name, level=level, subject=subject_name, size=size)
        
        self.node_count += 1
        if self.node_count % 50 == 0:
            print(f"已创建 {self.node_count} 个节点...")
        
        # 创建关系到父节点
        session.run("""
            MATCH (child:Concept {name: $child_name})
            MATCH (parent:Concept {name: $parent_name})
            MERGE (child)-[:BELONGS_TO]->(parent)
        """, child_name=current_name, parent_name=parent_name)
        
        self.relation_count += 1
        
        # 递归处理子节点
        if 'topics' in topic:
            for sub_topic in topic['topics']:
                self._traverse_and_create(session, sub_topic, current_name, subject_name, level + 1)

    def print_statistics(self):
        """打印统计信息"""
        with self.driver.session() as session:
            result = session.run("MATCH (n:Concept) RETURN count(n) as count")
            node_count = result.single()['count']
            
            result = session.run("MATCH ()-[r:BELONGS_TO]->() RETURN count(r) as count")
            relation_count = result.single()['count']
            
            print(f"\n{'='*50}")
            print(f"导入完成统计")
            print(f"{'='*50}")
            print(f"节点总数: {node_count}")
            print(f"关系总数: {relation_count}")
            
            # 按科目统计
            result = session.run("""
                MATCH (c:Concept)
                WHERE c.subject IS NOT NULL
                RETURN c.subject as subject, count(c) as count
                ORDER BY count DESC
            """)
            print(f"\n按科目统计:")
            for record in result:
                print(f"  - {record['subject']}: {record['count']} 个节点")


def main():
    xmind_dir = "/home/xmy/code/xmind"
    
    # XMind文件和科目名称映射
    xmind_files = [
        ("数据结构.xmind", "数据结构"),
        ("计算机组成.xmind", "计算机组成原理"),
        ("计算机操作系统.xmind", "操作系统"),
        ("计算机网络.xmind", "计算机网络"),
    ]
    
    importer = XMindToNeo4j(URI, USER, PASSWORD)
    
    try:
        print("开始导入408知识图谱到Neo4j...")
        print(f"数据库: {URI}")
        
        # 清空现有数据
        importer.clear_existing_data()
        
        # 创建根节点
        importer.create_root_node()
        
        # 导入所有XMind文件
        for filename, subject_name in xmind_files:
            file_path = os.path.join(xmind_dir, filename)
            if os.path.exists(file_path):
                importer.process_xmind(file_path, subject_name)
            else:
                print(f"警告: 文件不存在 {file_path}")
        
        # 打印统计信息
        importer.print_statistics()
        
        print("\n🎉 所有知识图谱导入完成！")
        print("可以在 Neo4j Browser (http://localhost:7474) 中查看")
        
    finally:
        importer.close()


if __name__ == "__main__":
    main()
