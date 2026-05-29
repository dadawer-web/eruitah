"""
RAG 自动化评测脚本

用法:
  cd e:\\needfix
  python scripts/run_rag_eval.py

流程:
  1. 初始化 RAG 引擎 + LLM 客户端
  2. 遍历内置测试用例
  3. 对每个用例: semantic_search → LLM 生成答案 → 三维评分
  4. 打印评测报告
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_CASES = [
    {
        "query": "什么是二叉树？请简述其基本性质",
        "expected_answer": "二叉树是每个节点最多有两个子节点的树结构，基本性质包括：第i层最多有2^(i-1)个节点，深度为k的二叉树最多有2^k-1个节点",
    },
    {
        "query": "Python中列表和元组有什么区别？",
        "expected_answer": "列表是可变的(mutable)，元组是不可变的(immutable)。列表用[]定义，元组用()定义。元组性能更好，可作为字典键。",
    },
    {
        "query": "请解释HTTP和HTTPS的区别",
        "expected_answer": "HTTPS是HTTP的安全版本，通过SSL/TLS加密传输数据，默认端口443而非80，需要CA证书，防止数据被窃听和篡改。",
    },
    {
        "query": "什么是微服务架构？它有哪些优缺点？",
        "expected_answer": "微服务架构将应用拆分为独立部署的小服务。优点：独立部署、技术栈灵活、故障隔离。缺点：分布式复杂性、数据一致性挑战、运维成本高。",
    },
    {
        "query": "机器学习中过拟合如何解决？",
        "expected_answer": "解决过拟合的方法包括：增加训练数据、正则化(L1/L2)、Dropout、早停法(Early Stopping)、交叉验证、数据增强、降低模型复杂度。",
    },
]

USER_ID = "eval-test-user-0000-1111-2222"


def _bar(score: int, width: int = 20) -> str:
    filled = int(score / 10 * width)
    empty = width - filled
    if score >= 8:
        color = "\033[92m"
    elif score >= 5:
        color = "\033[93m"
    else:
        color = "\033[91m"
    reset = "\033[0m"
    return f"{color}{'█' * filled}{'░' * empty}{reset} {score}/10"


def _print_report(results: list):
    W = 72
    print()
    print("╔" + "═" * W + "╗")
    print("║" + "  🔬 RAG 自动化评测报告".center(W - 2) + "║")
    print("╠" + "═" * W + "╣")

    all_faith = []
    all_ctx = []
    all_ans = []

    for i, r in enumerate(results):
        f = r["faithfulness"]
        c = r["context_relevance"]
        a = r["answer_relevance"]
        avg = r["average_score"]

        all_faith.append(f["score"])
        all_ctx.append(c["score"])
        all_ans.append(a["score"])

        print(f"║  📋 用例 {i + 1}: {r['query'][:40]}..." + " " * (W - 52) + "║")
        print(f"║  ├─ 忠实度 (Faithfulness)      {_bar(f['score'])}" + " " * (W - 50) + "║")
        print(f"║  │  └─ {f['reason'][:50]}" + " " * (W - 55) + "║")
        print(f"║  ├─ 检索相关性 (Ctx Relevance)  {_bar(c['score'])}" + " " * (W - 50) + "║")
        print(f"║  │  └─ {c['reason'][:50]}" + " " * (W - 55) + "║")
        print(f"║  ├─ 回答相关性 (Ans Relevance)  {_bar(a['score'])}" + " " * (W - 50) + "║")
        print(f"║  │  └─ {a['reason'][:50]}" + " " * (W - 55) + "║")
        print(f"║  └─ 综合得分: {avg:.1f}/10" + " " * (W - 20) + "║")
        if i < len(results) - 1:
            print("║" + "─" * W + "║")

    print("╠" + "═" * W + "╣")

    n = len(results)
    avg_f = sum(all_faith) / n if n else 0
    avg_c = sum(all_ctx) / n if n else 0
    avg_a = sum(all_ans) / n if n else 0
    overall = (avg_f + avg_c + avg_a) / 3

    print(f"║  📊 系统级平均分".ljust(W + 1) + "║")
    print(f"║  ├─ 忠实度均值:      {avg_f:.1f}/10" + " " * (W - 30) + "║")
    print(f"║  ├─ 检索相关性均值:  {avg_c:.1f}/10" + " " * (W - 30) + "║")
    print(f"║  ├─ 回答相关性均值:  {avg_a:.1f}/10" + " " * (W - 30) + "║")
    print(f"║  └─ 🏆 综合平均分:   {overall:.1f}/10" + " " * (W - 30) + "║")

    if overall >= 8:
        grade = "🟢 优秀"
    elif overall >= 6:
        grade = "🟡 良好"
    elif overall >= 4:
        grade = "🟠 一般"
    else:
        grade = "🔴 较差"

    print(f"║  评级: {grade}" + " " * (W - 12) + "║")
    print("╚" + "═" * W + "╝")
    print()


async def run_eval():
    print("🚀 初始化评测环境...")

    from app.services.ai_client import UnifiedAIClient
    from app.services.rag_engine import RAGEngine
    from app.services.evaluator import RAGEvaluator

    llm_client = UnifiedAIClient()
    rag_engine = RAGEngine(ai_client=llm_client)
    evaluator = RAGEvaluator(llm_client=llm_client)

    print(f"📋 测试用例: {len(TEST_CASES)} 个")
    print(f"👤 评测用户: {USER_ID}")
    print()

    results = []

    for i, case in enumerate(TEST_CASES):
        query = case["query"]
        expected = case["expected_answer"]

        print(f"⏳ 评测用例 {i + 1}/{len(TEST_CASES)}: {query[:40]}...")

        context_parts = []
        try:
            search_results = await rag_engine.semantic_search(
                query=query, top_k=3, user_id=USER_ID
            )
            for r in search_results:
                content = r.get("content", r.get("page_content", ""))
                if content:
                    context_parts.append(content[:500])
        except Exception as e:
            print(f"  ⚠️ 检索失败: {e}")

        context_text = "\n\n".join(context_parts) if context_parts else "（未检索到相关上下文）"

        answer = ""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "请基于以下上下文回答用户问题。如果上下文不足以回答，请根据你的知识补充，但需明确标注。\n\n上下文：\n"
                    + context_text[:3000],
                },
                {"role": "user", "content": query},
            ]
            answer = await llm_client.acall_api(messages, max_tokens=1024) or ""
        except Exception as e:
            print(f"  ⚠️ 生成答案失败: {e}")
            answer = "（生成失败）"

        eval_result = await evaluator.evaluate_all(
            query=query, context=context_text, answer=answer
        )
        eval_result["query"] = query
        eval_result["expected_answer"] = expected
        eval_result["generated_answer"] = answer[:200]
        eval_result["context_length"] = len(context_text)

        results.append(eval_result)
        print(f"  ✅ 忠实度={eval_result['faithfulness']['score']} "
              f"检索相关性={eval_result['context_relevance']['score']} "
              f"回答相关性={eval_result['answer_relevance']['score']} "
              f"综合={eval_result['average_score']}")

    _print_report(results)

    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "eval_report.json",
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"📄 详细报告已保存: {report_path}")


if __name__ == "__main__":
    asyncio.run(run_eval())
