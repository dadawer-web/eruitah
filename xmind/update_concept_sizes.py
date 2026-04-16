#!/usr/bin/env python3
"""
为Neo4j中的知识点节点设置size属性
基于知识点层级计算size值：
- Level 0-1: 根节点/科目级 (size=10) - 极大概念，需要多次学习
- Level 2-3: 主要章节 (size=7-8) - 中大型概念
- Level 4-5: 具体知识点 (size=4-6) - 中等概念
- Level 6+: 细节考点 (size=1-3) - 小概念，容易掌握

size越小，单次答题对掌握度的贡献越大（alpha = 1/size）
"""

from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "12345678"

def calculate_size(level):
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

def update_concept_sizes():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (c:Concept)
                WHERE c.level IS NOT NULL
                RETURN c.name as name, c.level as level, c.subject as subject
            """)
            
            concepts = list(result)
            print(f"找到 {len(concepts)} 个知识点节点")
            
            updated = 0
            for record in concepts:
                name = record['name']
                level = record['level']
                subject = record['subject']
                size = calculate_size(level)
                
                session.run("""
                    MATCH (c:Concept {name: $name})
                    SET c.size = $size
                """, name=name, size=size)
                
                updated += 1
                if updated % 100 == 0:
                    print(f"已更新 {updated} 个节点...")
            
            print(f"\n✅ 成功更新 {updated} 个知识点的size属性")
            
            result = session.run("""
                MATCH (c:Concept)
                WHERE c.size IS NOT NULL
                RETURN c.size as size, count(c) as count
                ORDER BY c.size DESC
            """)
            
            print("\n按size分布统计:")
            for record in result:
                print(f"  size={record['size']}: {record['count']} 个节点")
            
            result = session.run("""
                MATCH (c:Concept)
                WHERE c.size IS NOT NULL AND c.level IS NOT NULL
                RETURN c.level as level, c.size as size, count(c) as count
                ORDER BY c.level
            """)
            
            print("\n按level和size分布统计:")
            for record in result:
                print(f"  level={record['level']}, size={record['size']}: {record['count']} 个节点")
                
    finally:
        driver.close()

if __name__ == "__main__":
    print("开始为知识点设置size属性...")
    print("算法说明:")
    print("  - Level 0-1 (科目级): size=10 (极大概念，如'计算机网络')")
    print("  - Level 2-3 (章节级): size=7-8 (中大型概念)")
    print("  - Level 4-5 (知识点): size=4-6 (中等概念)")
    print("  - Level 6+ (细节): size=2 (小概念，如'IP分片')")
    print()
    update_concept_sizes()
