import sys
import asyncio
import json
import logging
import os
import subprocess
import re

import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://token-plan-cn.xiaomimimo.com")
CAREER_MODEL = os.environ.get("CAREER_MODEL", "mimo-v2.5-pro")

MAX_DIFF_CHARS = 6000
MAX_CONTEXT_CHARS = 16000

SYSTEM_PROMPT = """你是一个极其严苛的大厂技术总监（前腾讯 T13 / 阿里 P9）。用户刚刚完成了一段真实的编程任务。
你的任务是阅读他们写的【真实代码】，提炼出写在简历上的【硬核技术亮点】。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【绝对禁令】（违反即判废品，你将被解雇！）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
以下词汇/句式绝对禁止出现在 resume_highlight 中：
- ❌ "通过编程任务" / "熟练掌握" / "展现了扎实基础"
- ❌ "构建核心逻辑" / "解决了关键难题" / "实现了核心功能"
- ❌ "运用了...技术" / "使用了...技术" / "基于XXX构建核心业务逻辑"
- ❌ "提高了问题解决能力" / "提升了开发效率" / "增强了...能力"
- ❌ "掌握了...核心技术" / "熟悉了..." / "学习了..."
- ❌ "成功实现了" / "完成了"（太空泛！必须说清实现了什么、解决了什么）
- ❌ "进行了异常处理" / "使用了面向对象" / "进行了代码优化"（笼统废话）
- ❌ 任何不能直接写在求职简历上的空话套话

自检规则：如果任何亮点读起来像"老师评语"而非"简历项目经验"，立即重写！

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【严禁幻觉 & 上下文边界】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⛔ 绝对红线：你只能基于下方提供的【git diff】进行分析！
如果 git diff 为空或没有有意义的代码变更，你必须返回空的 skills 列表和空的 resume_highlight！
绝对禁止输出 OpenAI、LangChain、LlamaIndex 等与 diff 无关的内容！
这些是沙盒基础设施的调用，不是用户写的代码！

- 你必须且只能从提供的真实代码上下文中推断技术栈，绝不允许凭空捏造
- 每个 skill 必须能在代码中找到直接证据（import 语句、函数调用、类继承等）
- 宁可少输出 2 个技能，也绝不多输出 1 个不相关的技能
- ⛔ 严禁输出与提供的代码 DIFF 或新建代码无关的基础框架信息！
  代码中出现的 OpenAI/LangChain 等调用可能是沙盒基础设施自动注入的，不是用户写的！
  你只能基于用户真正编写的业务代码来总结，绝不允许把框架调用当成用户的技术亮点！

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【技能提取优先级】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
你必须像扫描仪一样，提取代码中所有高价值的第三方库名、架构名词和核心概念！
例如 LangChain, FAISS, RAG, 向量检索, SpringCloud, MyBatis, Redis, Kafka 等。
技能数量不设上限，只要在代码里真实出现了就提取出来！

P0（至少占 50%）：算法名称、架构设计模式、核心业务概念
P1（不超过 30%）：领域框架/库（如 LangChain, FAISS, SpringCloud, MyBatis）
P2（不超过 20%）：通用基建工具
宁可多提取 3 个真实技能，也绝不遗漏代码中明确出现的技术栈词汇！

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【简历亮点强制格式】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 使用 `## 🚀 核心架构演进` 作为标题
2. 包含 2~3 个核心亮点，每个亮点占一个 Markdown 列表项
3. 总字数不少于 100 字，必须言之有物

每个亮点的强制拼装公式：
- **{2~4字核心领域}**：{具体动作动词} + {核心技术/工具} + {解决了什么业务难点/实现了什么具体功能} + {量化结果或技术细节}

必须指出代码中具体的库名、算法名或架构设计！

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【正确输出范例（必须模仿！）】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

范例一（C++ 内存池）：
## 🚀 核心架构演进
- **高性能内存池设计**：利用 `FixedBlockMemoryPool` 与模板元编程，避免了频繁的 `malloc/free`，彻底消除内存碎片问题。
- **零成本抽象线程安全**：基于策略模式与 `std::mutex`，设计 `ThreadSafePool` 装饰器，在编译期通过模板特化选择加锁策略，无锁路径零开销。

范例二（LangGraph 应用）：
## 🚀 核心架构演进
- **大模型编排层**：基于 LangChain 编排 OpenAI 接口，引入记忆切片机制，彻底解决了多轮长文本对话中的 Token 溢出与上下文遗忘问题。
- **状态机引擎**：独立实现 StateGraph 状态流转引擎，将 Agent 的多步推理过程从硬编码 if-else 重构为声明式 DAG 图，新增推理分支的代码量降低 70%。

范例三（高并发 ChatServer）：
## 🚀 核心架构演进
- **高并发网络层**：基于 epoll 多路复用与 Reactor 模式，独立实现了高可用的 ChatServer，单连接处理延迟低于 5ms。
- **粘包处理**：自定义 4 字节长度前缀通信协议，解决了 TCP 字节流的粘包与半包问题，保障了数据的绝对可靠传输。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【错误输出范例（绝对禁止！）】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- **技术实践**：通过编程任务，运用了 Python、图算法 等核心技术，展现了扎实的编程基础。  ← 全是禁语！
- **代码实现**：成功实现了一个 SpringBoot 应用，使用了 Spring MVC 和 MyBatis 框架。  ← 空话！没说解决了什么问题！
- **FreeList**：基于 FreeList 构建核心业务逻辑，解决了关键难题。  ← "构建核心逻辑""关键难题"全是禁语！

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【强关联代码上下文规则】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
你必须从代码中提取具体证据来支撑每个亮点，绝不允许笼统概括：
- 异常处理 → 必须指出"捕获了 {具体异常类型}，保障了 {具体模块} 的健壮性"
- 类继承 → 必须指出"继承 {父类} 实现了 {具体功能扩展}"
- 配置文件 → 必须指出"通过 {具体配置项} 实现了 {具体行为}"
- 内存管理 → 必须指出"利用 {具体机制} 避免了 {具体问题}"

核心原则：每个亮点中的技术细节，必须能让面试官在代码中找到对应实现！

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【输出格式】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⛔ 你必须且只能输出合法的 JSON 字符串！绝不能包含任何额外的解释性文本！
⛔ 绝不能用 ```json ... ``` 包裹你的输出！直接输出裸 JSON！
⛔ 如果你输出了任何 JSON 之外的内容（包括解释、注释、markdown标记），整个结果将被丢弃！

直接输出以下 JSON（不要包含任何其他文字、注释或 markdown 代码块标记）：
{
  "skills": ["内存池", "模板元编程", "CMake"],
  "resume_highlight": "## 🚀 核心架构演进\\n- **高性能内存池设计**：利用 `FixedBlockMemoryPool` 与模板元编程，避免了频繁的 `malloc/free`，彻底消除内存碎片问题。\\n- **零成本抽象线程安全**：基于策略模式与 `std::mutex`，设计 `ThreadSafePool` 装饰器，在编译期通过模板特化选择加锁策略，无锁路径零开销。",
  "next_suggestion": "建议下一步引入 tcmalloc 做性能基准对比，或使用 valgrind 检测内存泄漏。"
}

最终自检：① 无禁语？② 每个亮点都有具体技术细节？③ 总字数 ≥ 100？④ 所有 skill 在代码中有证据？⑤ 输出的是纯 JSON，没有 markdown 代码块标记？如有任何一项不满足，立即重写！"""

USER_PROMPT_TEMPLATE = """## 用户任务描述
{task_description}

## 代码变更记录 (git diff) —— 这是你唯一可依赖的输入！
```
{git_diff}
```

---
⛔ 绝对红线：你只能基于上方的 git diff 分析！如果 diff 中没有代码，直接返回空！绝对禁止输出 OpenAI、LangChain 等与 diff 无关的内容！

请**严格基于以上真实代码**分析用户的技术能力。记住：每个 skill 必须能在代码中找到直接证据，绝不允许捏造代码中不存在的技能。按指定 JSON 格式输出。"""


def clean_and_parse_json(raw_text: str) -> dict | None:
    if not raw_text or not raw_text.strip():
        logger.warning("[CareerAnalyzer] clean_and_parse_json: empty input")
        return None

    logger.info(f"[CareerAnalyzer] LLM raw response:\n{raw_text}")

    try:
        match = re.search(r'(\{[\s\S]*\})', raw_text)
        if match:
            json_str = match.group(1)
            result = json.loads(json_str)
            if isinstance(result, dict):
                logger.info(f"[CareerAnalyzer] JSON parsed successfully, keys={list(result.keys())}")
                return result
            logger.warning(f"[CareerAnalyzer] Parsed JSON is not a dict: {type(result)}")
            return None
        else:
            logger.error("[CareerAnalyzer] No JSON brace structure found in LLM response!")
            return None
    except json.JSONDecodeError as e:
        logger.error(f"[CareerAnalyzer] JSON parse failed: {e}\nAttempted text: {json_str[:500] if 'json_str' in dir() else raw_text[:500]}")
        return None


def get_real_diff(work_dir: str) -> str:
    try:
        allowed_exts = ('.py', '.cpp', '.c', '.h', '.hpp', '.java', '.js', '.ts', '.go', '.rs',
                        '.jsx', '.tsx', '.vue', '.svelte', '.scala', '.kt', '.rb', '.php',
                        '.cs', '.swift', '.m', '.mm', '.sh', '.sql', '.proto', '.gradle',
                        '.xml', '.yaml', '.yml', '.toml', '.cmake', '.makefile')

        changed_files_cmd = ['git', 'diff', 'HEAD~1', 'HEAD', '--name-only']
        changed_files_raw = subprocess.check_output(
            changed_files_cmd, cwd=work_dir, stderr=subprocess.STDOUT, timeout=15,
        )
        changed_files = changed_files_raw.decode('utf-8', errors='replace').strip().splitlines()

        valid_files = []
        for f in changed_files:
            f = f.strip()
            if not f:
                continue
            parts = f.split('/')
            is_hidden = any(p.startswith('.') for p in parts)
            if not is_hidden and f.endswith(allowed_exts):
                valid_files.append(f)

        if not valid_files:
            logger.warning(
                f"[CareerAnalyzer] No pure business code modified, blocking invalid analysis. "
                f"Changed files: {changed_files}"
            )
            return ""

        diff_cmd = ['git', 'diff', 'HEAD~1', 'HEAD', '--'] + valid_files
        diff_raw = subprocess.check_output(diff_cmd, cwd=work_dir, stderr=subprocess.STDOUT, timeout=15)

        return diff_raw.decode('utf-8', errors='replace')[:4000]
    except Exception as e:
        logger.error(f"[CareerAnalyzer] get_real_diff failed: {e}")
        return ""


def _collect_git_diff(work_dir: str, max_chars: int = MAX_DIFF_CHARS) -> str:
    if not work_dir or not os.path.isdir(work_dir):
        return ""

    diff_commands = [
        ["git", "diff", "HEAD~1", "HEAD", "--diff-filter=ACMR", "--"],
        ["git", "diff", "--cached", "--diff-filter=ACMR", "--"],
        ["git", "diff", "--diff-filter=ACMR", "--"],
    ]

    for cmd in diff_commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=15, cwd=work_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                diff = result.stdout.strip()
                if len(diff) > max_chars:
                    diff = diff[:max_chars] + "\n... (truncated)"
                return diff
        except Exception:
            continue

    fallback_commands = [
        ["git", "log", "--oneline", "-5"],
        ["git", "diff", "--stat", "HEAD~5", "HEAD"],
        ["git", "diff", "HEAD~5", "HEAD"],
    ]

    parts = []
    for cmd in fallback_commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                cwd=work_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts.append(result.stdout.strip())
        except Exception:
            continue

    combined = "\n\n".join(parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n... (truncated)"
    return combined


def _extract_task_description(session_messages: list) -> str:
    if not session_messages:
        return ""

    for msg in session_messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        if role == "user" and content and len(content) > 10:
            return content[:500]

    for msg in session_messages:
        content = str(msg.get("content", ""))
        if content and len(content) > 10:
            return content[:500]

    return ""


_IMPORT_PATTERN = re.compile(
    r'^\s*(?:import|from|require|include|#include|using)\s+[\w.*]+',
    re.MULTILINE,
)

def _extract_imports_from_code(code_content: str) -> set:
    matches = _IMPORT_PATTERN.findall(code_content)
    return set(m.strip().lower() for m in matches)


_STRICT_KEYWORD_MAP = {
    "pygame": "Pygame",
    "tkinter": "Tkinter",
    "qt": "Qt",
    "pyqt": "PyQt",
    "pyside": "PySide",
    "flask": "Flask",
    "django": "Django",
    "fastapi": "FastAPI",
    "sqlalchemy": "SQLAlchemy",
    "scrapy": "Scrapy",
    "celery": "Celery",
    "requests": "Requests",
    "aiohttp": "AIOHTTP",
    "httpx": "HTTPX",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scipy": "SciPy",
    "matplotlib": "Matplotlib",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "sklearn": "Scikit-learn",
    "opencv": "OpenCV",
    "pillow": "Pillow",
    "redis": "Redis",
    "mongodb": "MongoDB",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "grpc": "gRPC",
    "protobuf": "Protobuf",
    "netty": "Netty",
    "spring": "Spring",
    "mybatis": "MyBatis",
    "muduo": "Muduo",
    "epoll": "Epoll",
    "io_uring": "io_uring",
    "websocket": "WebSocket",
    "langgraph": "LangGraph",
    "langchain": "LangChain",
    "llamaindex": "LlamaIndex",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "streamlit": "Streamlit",
    "gradio": "Gradio",
    "jupyter": "Jupyter",
    "scrapy": "Scrapy",
    "celery": "Celery",
    "react": "React",
    "vue": "Vue",
    "angular": "Angular",
    "nextjs": "Next.js",
    "nuxt": "Nuxt",
    "tailwind": "TailwindCSS",
    "webpack": "Webpack",
    "vite": "Vite",
    "cmake": "CMake",
    "makefile": "Makefile",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "python": "Python",
    "java": "Java",
    "rust": "Rust",
}

_CODE_PATTERN_SKILLS = {
    "epoll_create": "Epoll",
    "epoll_ctl": "Epoll",
    "epoll_wait": "Epoll",
    "socket(": "Socket编程",
    "bind(": "网络编程",
    "listen(": "网络编程",
    "accept(": "网络编程",
    "pthread": "多线程",
    "std::thread": "多线程",
    "std::mutex": "多线程",
    "std::atomic": "原子操作",
    "asyncio": "AsyncIO",
    "async def": "异步编程",
    "await ": "异步编程",
    "class.*Exception": "异常处理",
    "try:": "异常处理",
    "unittest": "单元测试",
    "pytest": "Pytest",
    "def test_": "单元测试",
    "SELECT ": "SQL",
    "INSERT ": "SQL",
    "CREATE TABLE": "SQL",
    "dfs(": "深度优先搜索",
    "bfs(": "广度优先搜索",
    "binary_search(": "二分查找",
    "sort(": "排序算法",
    "hash_map": "哈希表",
    "binary_tree": "二叉树",
    "linked_list": "链表",
    "adjacency_list": "图算法",
    "adjacency_matrix": "图算法",
    "dijkstra": "Dijkstra算法",
    "topological_sort": "拓扑排序",
    "dynamic_programming": "动态规划",
    "backtrack(": "回溯算法",
    "pygame": "Pygame",
    "game_loop": "游戏循环",
    "collision": "碰撞检测",
    "sprite": "Sprite系统",
    "malloc": "内存管理",
    "free(": "内存管理",
    "MemoryPool": "内存池",
    "memory_pool": "内存池",
    "ObjectPool": "对象池",
    "object_pool": "对象池",
    "FixedBlock": "固定块内存池",
    "FreeList": "空闲链表",
    "free_list": "空闲链表",
    "template<": "模板元编程",
    "typename": "模板元编程",
    "std::allocator": "内存分配器",
    "new(": "内存管理",
    "delete ": "内存管理",
    "mmap": "内存映射",
    "virtual_memory": "虚拟内存",
    "RAII": "RAII",
    "smart_ptr": "智能指针",
    "shared_ptr": "智能指针",
    "unique_ptr": "智能指针",
}


def _fallback_skills_from_code(code_content: str, diff_text: str) -> list:
    combined_lower = (code_content + " " + diff_text).lower()
    combined_original = code_content + " " + diff_text
    imports = _extract_imports_from_code(code_content + "\n" + diff_text)

    found = set()

    for kw, skill_name in _STRICT_KEYWORD_MAP.items():
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, combined_lower):
            found.add(skill_name)

    for pattern_str, skill_name in _CODE_PATTERN_SKILLS.items():
        try:
            if re.search(pattern_str, combined_lower):
                found.add(skill_name)
        except re.error:
            if pattern_str in combined_lower:
                found.add(skill_name)

    for imp in imports:
        for kw, skill_name in _STRICT_KEYWORD_MAP.items():
            if kw in imp:
                found.add(skill_name)

    _TASK_DESC_SKILLS = {
        "springboot": "SpringBoot",
        "spring boot": "SpringBoot",
        "spring-boot": "SpringBoot",
        "langgraph": "LangGraph",
        "langchain": "LangChain",
        "react": "React",
        "vue": "Vue",
        "flask": "Flask",
        "django": "Django",
        "fastapi": "FastAPI",
        "贪吃蛇": "Pygame",
        "游戏": "游戏开发",
        "聊天": "网络编程",
        "机器学习": "机器学习",
        "深度学习": "深度学习",
        "爬虫": "网络爬虫",
        "数据库": "数据库",
        "微服务": "微服务架构",
        "docker": "Docker",
        "k8s": "Kubernetes",
        "redis": "Redis",
        "算法": "算法设计",
        "排序": "排序算法",
        "二叉树": "二叉树",
        "链表": "链表",
        "编译器": "编译器",
        "操作系统": "操作系统",
        "内存池": "内存池",
        "对象池": "对象池",
        "内存管理": "内存管理",
        "内存分配": "内存管理",
        "连接池": "连接池",
        "线程池": "线程池",
    }
    for kw, skill_name in _TASK_DESC_SKILLS.items():
        if kw in combined_original.lower():
            found.add(skill_name)

    return sorted(found)[:8]


async def _call_llm(system_prompt: str, user_prompt: str) -> dict | None:
    url = f"{OPENAI_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": CAREER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(url, headers=headers, json=payload)

                if resp.status_code == 400:
                    error_body = resp.text[:500]
                    logger.error(f"[CareerAnalyzer] LLM 400 Bad Request (attempt {attempt+1}): {error_body}")
                    if attempt == 0:
                        payload["messages"][1]["content"] = user_prompt[:4000]
                        logger.info("[CareerAnalyzer] Retrying with truncated prompt...")
                        continue
                    return None

                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

                result = clean_and_parse_json(content)
                if result is not None:
                    return result

                logger.warning(f"[CareerAnalyzer] LLM output could not be parsed as valid JSON, raw: {content[:200]}")
                return None
        except httpx.TimeoutException:
            logger.error(f"[CareerAnalyzer] LLM call timed out (45s, attempt {attempt+1})")
            if attempt == 0:
                continue
            return None
        except Exception as e:
            logger.error(f"[CareerAnalyzer] LLM call failed (attempt {attempt+1}): {e}")
            if attempt == 0:
                continue
            return None

    return None


def _build_fallback_result(
    skills: list,
    task_description: str,
    diff_summary: str,
) -> dict:
    if not skills:
        return {
            "skills": [],
            "resume_highlight": "",
            "next_suggestion": "",
        }

    top_skills = skills[:5]

    highlights = [f"## 🚀 核心架构演进"]

    task_brief = task_description[:40] if task_description else "本次编程任务"

    if len(top_skills) >= 2:
        highlights.append(
            f"- **{top_skills[0]}**：基于 {top_skills[0]} 实现了{task_brief}中的关键模块，"
            f"解决了核心技术挑战。"
        )
        highlights.append(
            f"- **{top_skills[1]}**：集成 {top_skills[1]} 优化了系统架构，"
            f"保障了数据流的可靠性与性能。"
        )
    elif len(top_skills) == 1:
        highlights.append(
            f"- **{top_skills[0]}**：基于 {top_skills[0]} 实现了{task_brief}中的关键模块，"
            f"解决了核心技术挑战。"
        )

    if diff_summary:
        highlights.append(f"- **代码产出**：{diff_summary[:200]}")

    highlight = "\n".join(highlights)

    return {
        "skills": skills,
        "resume_highlight": highlight,
        "next_suggestion": f"建议深入学习 {skills[0]} 相关的高级特性与生产级最佳实践。" if skills else "",
    }


def _validate_skills_against_code(skills: list, code_content: str, diff_text: str) -> list:
    if not skills:
        return []

    combined_lower = (code_content + " " + diff_text).lower()
    validated = []

    for skill in skills:
        skill_lower = skill.lower()

        if skill_lower in combined_lower:
            validated.append(skill)
            continue

        skill_words = skill_lower.replace('+', ' ').replace('#', ' ').split()
        if len(skill_words) >= 2:
            if any(w in combined_lower for w in skill_words if len(w) > 2):
                validated.append(skill)
                continue

        known_aliases = {
            "c++": ["cpp", "c++", ".cpp", ".hpp"],
            "c#": ["c#", "csharp", ".cs"],
            "python": ["python", ".py", "import "],
            "javascript": ["javascript", ".js", "const ", "let ", "var "],
            "typescript": ["typescript", ".ts", ": string", ": number"],
            "java": ["java", ".java", "public class", "system.out"],
            "rust": ["rust", ".rs", "fn main", "let mut"],
            "go": ["golang", ".go", "func main", "package main"],
            "react": ["react", "usestate", "useeffect", "jsx"],
            "vue": ["vue", "v-if", "v-for", "ref(", "reactive("],
            "epoll": ["epoll", "epoll_create", "epoll_wait"],
            "muduo": ["muduo", "muduo::net"],
            "pygame": ["pygame", "pygame.init", "pygame.display"],
            "flask": ["flask", "from flask"],
            "django": ["django", "from django"],
            "fastapi": ["fastapi", "from fastapi"],
            "sql": ["select ", "insert ", "create table", "sql"],
            "html": ["<html", "<div", "<span", "html"],
            "css": ["css", "style=", "stylesheet"],
            "docker": ["docker", "dockerfile", "container"],
            "redis": ["redis", "redis://"],
            "mysql": ["mysql", "mysql://"],
            "mongodb": ["mongodb", "mongo://"],
            "kafka": ["kafka", "kafka://"],
            "protobuf": ["protobuf", ".proto", "proto3"],
            "grpc": ["grpc", "grpc://"],
            "websocket": ["websocket", "ws://", "wss://"],
            "多线程": ["thread", "mutex", "lock", "concurrent", "pthread"],
            "异步编程": ["async", "await", "asyncio", "promise", "future"],
            "网络编程": ["socket", "tcp", "udp", "listen", "bind", "accept"],
            "langgraph": ["langgraph", "from langgraph"],
            "langchain": ["langchain", "from langchain"],
            "llamaindex": ["llamaindex", "from llama_index"],
            "openai": ["openai", "from openai"],
            "数据结构": ["binary tree", "linked list", "hash table", "stack", "queue", "heap", "red-black"],
            "图算法": ["adjacency_list", "adjacency_matrix", "dijkstra", "topological_sort", "graph_traversal"],
            "排序算法": ["sort", "merge sort", "quick sort", "bubble"],
            "二分查找": ["binary search", "bisect"],
            "动态规划": ["dynamic programming", "dp[", "memo"],
            "回溯算法": ["backtrack", "dfs", "recursive"],
            "碰撞检测": ["collision", "collide", "intersect"],
            "游戏循环": ["game loop", "pygame", "main loop", "tick"],
            "内存池": ["memorypool", "memory_pool", "objectpool", "object_pool", "fixedblock", "freelist", "free_list", "allocator"],
            "内存管理": ["malloc", "free(", "new(", "delete ", "mmap", "raii", "smart_ptr", "shared_ptr", "unique_ptr"],
            "模板元编程": ["template<", "typename", "constexpr", "sfinae", "enable_if"],
            "智能指针": ["shared_ptr", "unique_ptr", "weak_ptr", "make_shared", "make_unique"],
            "线程池": ["threadpool", "thread_pool", "threadpoolexecutor"],
        }

        matched = False
        for canonical, aliases in known_aliases.items():
            if skill_lower == canonical or skill_lower in aliases:
                if any(a in combined_lower for a in aliases):
                    validated.append(skill)
                    matched = True
                break

        if not matched and len(skill) <= 5:
            pass

    return validated


async def analyze_career(
    user_id: int,
    work_dir: str,
    session_messages: list | None = None,
) -> dict | None:
    logger.info(f"[CareerAnalyzer] 🧠 Starting deep analysis for user={user_id}")

    git_diff = get_real_diff(work_dir)
    code_content = ""
    task_description = _extract_task_description(session_messages or [])

    if not git_diff and not task_description:
        logger.warning(f"[CareerAnalyzer] No context at all for user={user_id}")
        return None

    if not git_diff:
        logger.info(f"[CareerAnalyzer] No code files, using task description only for user={user_id}")
        fallback_skills = _fallback_skills_from_code(task_description, "")
        if fallback_skills:
            result = _build_fallback_result(fallback_skills, task_description, "")
            logger.info(f"[CareerAnalyzer] Task-desc fallback: skills={fallback_skills}")
            return result
        return None

    context_chars = len(git_diff) + len(task_description)
    logger.info(
        f"[CareerAnalyzer] Context size: "
        f"diff={len(git_diff)}, task_desc={len(task_description)}, "
        f"total={context_chars}"
    )

    logger.info(f"🔍 准备发送给 LLM 的 git diff:\n{git_diff[:500]}...")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        task_description=task_description or "(无任务描述)",
        code_content="(代码内容已包含在上方 git diff 中)",
        git_diff=git_diff or "(无 git diff)",
    )

    result = None
    if OPENAI_API_KEY:
        result = await _call_llm(SYSTEM_PROMPT, user_prompt)

    if result is not None:
        raw_skills = result.get("skills", [])
        validated = _validate_skills_against_code(raw_skills, git_diff, "")
        removed = [s for s in raw_skills if s not in validated]
        if removed:
            logger.info(f"[CareerAnalyzer] Filtered hallucinated skills: {removed}")
        result["skills"] = validated
        if not result.get("resume_highlight"):
            result["resume_highlight"] = ""
        if not result.get("learningAdvice") and not result.get("next_suggestion"):
            result["learningAdvice"] = ""

    if result is None:
        logger.info(f"[CareerAnalyzer] LLM unavailable or failed, using keyword fallback for user={user_id}")
        fallback_skills = _fallback_skills_from_code(git_diff, "")
        diff_summary = ""
        if git_diff:
            stat_lines = [l for l in git_diff.split("\n") if "|" in l or "file" in l.lower()]
            diff_summary = "; ".join(stat_lines[:3])
        result = _build_fallback_result(fallback_skills, task_description, diff_summary)

    if not result.get("skills") and not result.get("resume_highlight"):
        logger.warning(f"[CareerAnalyzer] Empty analysis result for user={user_id}, result keys={list(result.keys()) if result else 'None'}")
        return None

    logger.info(
        f"[CareerAnalyzer] ✅ Analysis complete for user={user_id}: "
        f"skills={result.get('skills', [])}, "
        f"highlight_len={len(result.get('resume_highlight', ''))}"
    )

    return result


def analyze_career_sync(
    user_id: int,
    work_dir: str,
    session_messages: list | None = None,
) -> dict | None:
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                analyze_career(user_id, work_dir, session_messages),
            )
            return future.result(timeout=60)
    else:
        return asyncio.run(analyze_career(user_id, work_dir, session_messages))
