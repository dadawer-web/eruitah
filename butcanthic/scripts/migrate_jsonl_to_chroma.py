"""
数据迁移脚本 - 将旧 JSONL 知识库数据导入 ChromaDB 向量数据库
用法: python scripts/migrate_jsonl_to_chroma.py [--source kb_data] [--target chroma_db]
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.rag_engine import RAGEngine


async def migrate_collection(
    rag: RAGEngine,
    collection_name: str,
    records_file: str,
):
    if not os.path.exists(records_file):
        print(f"  ⚠️  跳过 {collection_name}: 无 records.jsonl")
        return 0

    records = []
    with open(records_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not records:
        print(f"  ⚠️  跳过 {collection_name}: 无有效记录")
        return 0

    result = await rag.ingest_data({"records": records}, collection_name)
    count = result["ingested_count"]
    print(f"  ✅ {collection_name}: 导入 {count} 条记录")
    return count


async def main(source_dir: str, target_dir: str, api_key: str = None):
    print(f"🚀 开始数据迁移")
    print(f"   源目录: {source_dir}")
    print(f"   目标库: {target_dir}")

    rag = RAGEngine(
        persist_directory=target_dir,
        embedding_api_key=api_key,
    )

    collections_dir = os.path.join(source_dir, "collections")
    if not os.path.isdir(collections_dir):
        print(f"❌ 集合目录不存在: {collections_dir}")
        return

    total = 0
    for entry in sorted(os.listdir(collections_dir)):
        entry_path = os.path.join(collections_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        records_file = os.path.join(entry_path, "records.jsonl")
        count = await migrate_collection(rag, entry, records_file)
        total += count

    collections = await rag.list_collections()
    print(f"\n📊 迁移完成:")
    print(f"   总导入记录: {total}")
    print(f"   向量库集合: {len(collections)}")
    for coll in collections:
        print(f"     - {coll['name']}: {coll['count']} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="迁移 JSONL 知识库到 ChromaDB")
    parser.add_argument("--source", default="mulu/kb_data", help="JSONL 知识库目录")
    parser.add_argument("--target", default="chroma_db", help="ChromaDB 持久化目录")
    parser.add_argument("--api-key", default=None, help="DashScope API Key (或设置 DASHSCOPE_API_KEY 环境变量)")
    args = parser.parse_args()

    asyncio.run(main(args.source, args.target, args.api_key))
