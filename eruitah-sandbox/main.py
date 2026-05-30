"""
Eruitah 智能编程沙盒 - FastAPI Web 服务 v4

v4 完全重写: 对齐用户伪代码的"神经系统"模式

架构:
┌──────────────┐    WebSocket     ┌──────────────────┐     API      ┌──────────┐
│  Qt/C++ 客户端 │ <─────────────> │  FastAPI (本模块)  │ ──────────> │  LLM API  │
│  Monaco Editor │   双向实时通信   │  main.py v4       │ <────────── │  Claude   │
└──────────────┘                  └──────────────────┘              └──────────┘

核心设计:
  run_agent() 是同步生成器 → 通过 run_in_executor 放入线程池执行
  → 主线程 async for 遍历 → websocket.send_json() 实时推送

WebSocket 事件 (直接从 run_agent yield 出来):
  {"type": "status",     "data": "Agent 正在思考..."}
  {"type": "message",    "content": "大模型回复"}
  {"type": "tool_start", "tool_name": "bash", "args": {...}}
  {"type": "tool_end",   "tool_name": "bash", "result": "...", "is_error": false}
  {"type": "finish",     "data": "最终结果"}
  {"type": "error",      "data": "错误信息"}
"""

import os
import sys
import subprocess
import json
import time
import asyncio
import logging
import uuid
from typing import Optional
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件（优先从项目根目录加载）
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"已加载环境变量文件: {env_path}")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_runner import run_agent, MAX_TURNS
from agent_swarm import run_swarm

logger = logging.getLogger(__name__)

# ============================================================================
# 配置
# ============================================================================

SANDBOX_DIR = os.environ.get("ERUITAH_SANDBOX_DIR", "/tmp/eruitah-sandbox")
API_PROVIDER = os.environ.get("ERUITAH_API_PROVIDER", "openai")
DEFAULT_MODEL_OPENAI = os.environ.get("ERUITAH_MODEL_OPENAI", "gpt-4o")
DEFAULT_MODEL_ANTHROPIC = os.environ.get("ERUITAH_MODEL_ANTHROPIC", "claude-sonnet-4-20250514")
USE_SUBPROCESS_AGENT = os.environ.get("ERUITAH_USE_SUBPROCESS", "true").lower() == "true"

_stop_agent_flags: dict[str, bool] = {}
_active_agent_threads: dict[str, dict] = {}

def set_stop_flag(session_id: str, stop: bool = True):
    _stop_agent_flags[session_id] = stop
    if stop:
        logger.info(f"🛑 设置停止标志: session={session_id}")
        _force_kill_agent_resources(session_id)

def check_stop_flag(session_id: str) -> bool:
    return _stop_agent_flags.get(session_id, False)

def clear_stop_flag(session_id: str):
    _stop_agent_flags.pop(session_id, None)

def register_agent_thread(session_id: str, thread, future=None):
    _active_agent_threads[session_id] = {
        "thread": thread,
        "future": future,
        "created_at": __import__("time").time(),
    }

def unregister_agent_thread(session_id: str):
    _active_agent_threads.pop(session_id, None)

def _force_kill_agent_resources(session_id: str):
    info = _active_agent_threads.get(session_id)
    if not info:
        return

    try:
        from bash_executor import kill_active_process
        kill_active_process(session_id)
        logger.info(f"🛑 已强杀 session={session_id} 的 bash 子进程")
    except Exception as e:
        logger.debug(f"强杀 bash 子进程时异常（可能无运行中进程）: {e}")

    if USE_SUBPROCESS_AGENT:
        try:
            from agent_process import kill_agent_process
            kill_agent_process(session_id)
            logger.info(f"🛑 已强杀 session={session_id} 的 Agent 子进程")
        except Exception as e:
            logger.debug(f"强杀 Agent 子进程时异常: {e}")

    future = info.get("future")
    if future and not future.done():
        future.cancel()
        logger.info(f"🛑 已取消 session={session_id} 的 Agent Future")

    thread = info.get("thread")
    if thread and thread.is_alive():
        logger.info(f"🛑 session={session_id} 的 Agent 线程仍在运行，已标记为取消")


# ============================================================================
# 请求模型
# ============================================================================

class ExecuteRequest(BaseModel):
    prompt: str = Field(..., description="用户提示词", min_length=1)
    work_dir: Optional[str] = Field(None, description="工作目录")
    max_turns: int = Field(MAX_TURNS, description="最大循环轮数", ge=1, le=50)
    api_key: Optional[str] = Field(None, description="API Key")
    model: Optional[str] = Field(None, description="模型名称")
    base_url: Optional[str] = Field(None, description="API 基础 URL")
    provider: Optional[str] = Field(None, description="API 提供商: openai 或 anthropic")


class HealthResponse(BaseModel):
    status: str = "ok"
    sandbox_dir: str = ""
    api_provider: str = ""


# ============================================================================
# 应用生命周期
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info(f"Eruitah 沙盒服务 v4 启动，工作目录: {SANDBOX_DIR}")

    from sandbox_manager import init_global_sandbox
    sandbox = init_global_sandbox(pool_size=3)
    logger.info(
        f"🏗️ 全局 GitSandboxManager 已在启动时初始化: "
        f"BASE_REPO={sandbox.workspace_dir}, WORKTREES_ROOT={sandbox.worktree_base}"
    )

    yield

    from sandbox_manager import get_global_sandbox
    sb = get_global_sandbox()
    if sb:
        sb.shutdown()
    logger.info("Eruitah 沙盒服务关闭")


app = FastAPI(
    title="Eruitah 智能编程沙盒",
    description="基于 Claude Code 核心逻辑的 AI 编程沙盒微服务 v4",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_cross_origin_isolation_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    return response

# 挂载静态文件目录
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 挂载 Vue 前端 dist 目录（优先级高于内置 IDE 页面）
VUE_DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "coding-agent-ui", "dist")
_vue_dist_dir_resolved = os.path.realpath(VUE_DIST_DIR)
if os.path.isdir(_vue_dist_dir_resolved) and os.path.isfile(os.path.join(_vue_dist_dir_resolved, "index.html")):
    app.mount("/assets", StaticFiles(directory=os.path.join(_vue_dist_dir_resolved, "assets")), name="vue-assets")
    logger.info(f"Vue 前端 dist 已挂载: {_vue_dist_dir_resolved}")


# ============================================================================
# 同步生成器 → 异步迭代器 适配器
# ============================================================================

async def _run_agent_async(
    user_input: str,
    work_dir: str = ".",
    max_turns: int = MAX_TURNS,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: str = "openai",
    initial_messages: Optional[list] = None,
    start_turn: int = 1,
    task_id: Optional[str] = None,
    main_repo_dir: Optional[str] = None,
    auto_approve: bool = False,
    use_swarm: bool = False,
    user_id: int = 0,
    enable_routing: bool = False,
    images: Optional[list] = None,
    skills: Optional[list] = None,
):
    """
    绝对网关架构 (Absolute Gateway)

    ┌────────────────────────────────────────────────────────────────┐
    │  所有新任务必须先经过 Supervisor（CTO）审题                      │
    │  Supervisor 决定穿什么"专家外衣"，然后根据模式分发：              │
    │                                                                │
    │  极速模式 (use_swarm=False): 单体 Agent 穿专家外衣干活           │
    │  深度模式 (use_swarm=True):  红蓝对抗，蓝军穿专家外衣写代码       │
    │                                                                │
    │  继续任务 (initial_messages 非空): 跳过路由，直接继续             │
    └────────────────────────────────────────────────────────────────┘
    """
    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _sync_worker():
        try:
            if USE_SUBPROCESS_AGENT:
                from agent_process import start_agent_process

                config = {
                    "user_input": user_input,
                    "work_dir": work_dir,
                    "max_turns": max_turns,
                    "api_key": api_key,
                    "model": model,
                    "base_url": base_url,
                    "provider": provider,
                    "initial_messages": initial_messages,
                    "start_turn": start_turn,
                    "task_id": task_id,
                    "main_repo_dir": main_repo_dir,
                    "auto_approve": auto_approve,
                    "use_swarm": use_swarm,
                    "user_id": user_id,
                    "enable_routing": enable_routing,
                    "images": images or [],
                    "skills": skills,
                }

                process, event_queue = start_agent_process(
                    task_id or "default", config
                )

                import queue as queue_mod
                while True:
                    try:
                        event = event_queue.get(timeout=1.0)
                    except queue_mod.Empty:
                        if not process.is_alive():
                            try:
                                event = event_queue.get(timeout=0.5)
                                if event is None:
                                    break
                                loop.call_soon_threadsafe(queue.put_nowait, event)
                            except queue_mod.Empty:
                                if process.exitcode and process.exitcode < 0:
                                    loop.call_soon_threadsafe(queue.put_nowait, {
                                        "type": "error",
                                        "data": f"Agent 子进程异常退出 (signal={-process.exitcode})",
                                    })
                                break
                        continue

                    if event is None:
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, event)

            else:
                is_new_task = not initial_messages

                route_result = None
                expert_label = ""
                persona_prompt = ""
                effective_input = user_input
                effective_images = images or []

                from agent_runner import build_system_prompt

                if is_new_task and user_input:
                    if effective_images:
                        from agent_prompts import VISION_ARCHITECT_EXPERT

                        route_result = {
                            "is_predefined": True,
                            "target_agent_name": "vision_architect",
                            "dynamic_system_prompt": "",
                            "sub_task": user_input if not user_input.startswith("分析图片") else user_input,
                        }
                        expert_label = "vision_architect (视觉架构师)"
                        effective_input = user_input

                        base_prompt = build_system_prompt(work_dir)
                        persona_prompt = f"{base_prompt}\n\n# 🎯 专家身份激活\n你当前以 **视觉架构师** 专家身份执行任务。以下是你的专家指导原则：\n\n{VISION_ARCHITECT_EXPERT}"

                        logger.info(
                            f"[Supervisor] 检测到图片输入，直接指定视觉架构师 | 图片数: {len(effective_images)}"
                        )
                    else:
                        loop.call_soon_threadsafe(queue.put_nowait, {
                            "type": "status",
                            "data": "正在分析任务，选择专家...",
                        })

                        from agent_runner import route_task
                        route_result = route_task(
                            user_message=user_input,
                            api_key=api_key,
                            model=model,
                            base_url=base_url,
                            provider=provider,
                            images=effective_images,
                        )

                        is_predefined = route_result.get("is_predefined", True)
                        target_agent = route_result.get("target_agent_name", "general_coder")
                        sub_task = route_result.get("sub_task", user_input)
                        dynamic_prompt = route_result.get("dynamic_system_prompt", "")
                        cto_execution_env = route_result.get("execution_env", "native")

                        expert_label = target_agent if is_predefined else "动态生成的专家"
                        effective_input = sub_task

                        logger.info(
                            f"[Supervisor] 需求拆解完毕，已生成动态专家设定: {expert_label}，"
                            f"子任务: {sub_task[:80]}，执行环境: {cto_execution_env}"
                        )

                        loop.call_soon_threadsafe(queue.put_nowait, {
                            "type": "task_routed",
                            "data": {
                                "is_predefined": is_predefined,
                                "target_agent": target_agent,
                                "sub_task": sub_task,
                                "dynamic_prompt_length": len(dynamic_prompt) if dynamic_prompt else 0,
                                "mode": "deep" if use_swarm else "fast",
                                "execution_env": cto_execution_env,
                            },
                        })

                        base_prompt = build_system_prompt(work_dir)

                        if dynamic_prompt:
                            persona_prompt = f"{base_prompt}\n\n# 🎯 专家身份激活\n你当前以 **{expert_label}** 专家身份执行任务。以下是你的专家指导原则：\n\n{dynamic_prompt}"
                        elif not is_predefined and target_agent == "general_coder":
                            persona_prompt = ""
                        else:
                            from agent_prompts import get_expert_prompt
                            ep = get_expert_prompt(target_agent)
                            if ep:
                                persona_prompt = f"{base_prompt}\n\n# 🎯 专家身份激活\n你当前以 **{target_agent}** 专家身份执行任务。以下是你的专家指导原则：\n\n{ep}"
                            else:
                                persona_prompt = ""

                if skills and is_new_task:
                    from prompt_builder import get_prompt_builder
                    builder = get_prompt_builder()
                    skill_prompt = builder.build_skill_prompt(skills)
                    if skill_prompt:
                        if persona_prompt:
                            persona_prompt = f"{persona_prompt}\n\n{'=' * 60}\n# 🎯 附加技能激活\n{'=' * 60}\n\n{skill_prompt}"
                        else:
                            base_prompt = build_system_prompt(work_dir)
                            persona_prompt = f"{base_prompt}\n\n{'=' * 60}\n# 🎯 技能激活\n{'=' * 60}\n\n{skill_prompt}"
                        logger.info(f"📋 [Gateway] 技能提示词已注入: {skills}")

                plan_mode = bool(skills and "plan" in skills)
                if plan_mode:
                    logger.info(f"🔒 [Gateway] PM需求澄清模式已激活: 工具将被隔离为 ask_user + file_edit/file_write/file_read/glob/grep")

                sdd_mode = bool(skills and "sdd" in skills)

                if sdd_mode and is_new_task:
                    logger.info(f"🤖 [Gateway] SDD 多智能体协作模式 | task_id={task_id}")

                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "type": "sdd_loop_start",
                        "data": {"task_id": task_id, "task": effective_input[:100]},
                    })

                    from agent_swarm import run_sdd_loop
                    for event in run_sdd_loop(
                        task=effective_input,
                        work_dir=work_dir,
                        provider=provider,
                        api_key=api_key,
                        model=model,
                        base_url=base_url,
                        main_repo_dir=main_repo_dir,
                        task_id=task_id,
                        yield_events=True,
                        images=effective_images,
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, event)

                elif use_swarm and is_new_task and persona_prompt:
                    logger.info(
                        f"🧠 [Gateway] 深度模式 → 红蓝对抗 | 专家: {expert_label} | task_id={task_id}"
                    )

                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "type": "debate_loop_start",
                        "data": {
                            "expert_label": expert_label,
                            "sub_task": effective_input,
                            "dynamic_persona": bool(persona_prompt),
                        },
                    })

                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "type": "system_alert",
                        "content": f"⚔️ 红蓝对抗引擎启动！蓝军继承 [{expert_label}] 专家身份，红军从该领域最佳实践角度深度挑刺",
                    })

                    from agent_swarm import start_debate_loop
                    for event in start_debate_loop(
                        task=effective_input,
                        dynamic_persona_prompt=persona_prompt,
                        work_dir=work_dir,
                        provider=provider,
                        api_key=api_key,
                        model=model,
                        base_url=base_url,
                        max_loops=3,
                        main_repo_dir=main_repo_dir,
                        task_id=task_id,
                        auto_approve=auto_approve,
                        yield_events=True,
                        images=effective_images,
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, event)

                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "type": "debate_loop_end",
                        "data": {"expert_label": expert_label},
                    })

                elif use_swarm:
                    logger.info(f"🧠 [Gateway] 深度模式 → 直接红蓝对抗 (继续任务), task_id={task_id}")
                    for event in run_swarm(
                        user_input=user_input,
                        work_dir=work_dir,
                        max_turns=max_turns,
                        api_key=api_key,
                        model=model,
                        base_url=base_url,
                        provider=provider,
                        initial_messages=initial_messages,
                        start_turn=start_turn,
                        task_id=task_id,
                        main_repo_dir=main_repo_dir,
                        auto_approve=auto_approve,
                        yield_events=True,
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, event)

                else:
                    mode_tag = f"穿 [{expert_label}] 专家外衣" if persona_prompt else "默认全栈"
                    logger.info(
                        f"⚡ [Gateway] 极速模式 → 单体 Agent {mode_tag} | task_id={task_id}"
                    )

                    if persona_prompt:
                        loop.call_soon_threadsafe(queue.put_nowait, {
                            "type": "system_alert",
                            "content": f"🎯 专家身份激活: {expert_label}，单体极速模式执行",
                        })

                    for event in run_agent(
                        user_input=effective_input,
                        work_dir=work_dir,
                        max_turns=max_turns,
                        api_key=api_key,
                        model=model,
                        base_url=base_url,
                        provider=provider,
                        initial_messages=initial_messages,
                        start_turn=start_turn,
                        task_id=task_id,
                        main_repo_dir=main_repo_dir,
                        auto_approve=auto_approve,
                        user_id=user_id,
                        override_system_prompt=persona_prompt if persona_prompt else None,
                        images=effective_images,
                        plan_mode=plan_mode,
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, event)

        except Exception as e:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "data": f"Agent 内部异常: {str(e)}"},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    # 在线程池中启动同步生成器
    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    agent_future = loop.run_in_executor(executor, _sync_worker)

    import threading
    for t in threading.enumerate():
        if t.name.startswith("ThreadPoolExecutor"):
            register_agent_thread(task_id or "default", t, agent_future)
            break

    # 从队列中消费事件
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event

    unregister_agent_thread(task_id or "default")


async def _run_swarm_async(
    task_description: str,
    work_dir: str = ".",
    provider: str = "openai",
    api_key: str = None,
    model: str = None,
    base_url: str = None,
    max_loops: int = 5,
    main_repo_dir: str = "",
):
    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _sync_worker():
        try:
            for event in run_swarm(
                task_description=task_description,
                work_dir=work_dir,
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                max_loops=max_loops,
                main_repo_dir=main_repo_dir,
                yield_events=True,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as e:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "data": f"Swarm 内部异常: {str(e)}"},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    loop.run_in_executor(executor, _sync_worker)

    while True:
        event = await queue.get()
        if event is None:
            break
        yield event


# ============================================================================
# 系统指令拦截器 - 绕过大模型，0 Token 消耗
# ============================================================================

async def _handle_system_command(websocket, data: dict, safe_send):
    """
    网关拦截器：系统指令绝不经过大模型

    前端发送: {"type": "system_command", "action": "rollback_task|list_tasks|stop_agent|...", ...}
    后端直接执行 Python 函数，Agent 完全不知道发生了什么
    """
    from task_manager import get_session_manager

    action = data.get("action", "")
    task_id = data.get("task_id", "")
    work_dir = data.get("work_dir", SANDBOX_DIR)
    user_id = data.get("user_id", 0)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 0
    if not user_id:
        user_id = 1
        logger.warning(f"_handle_system_command: user_id missing in message, falling back to 1")

    sm = get_session_manager(user_id=user_id)

    if action == "list_tasks":
        tasks = sm.list_sessions(work_dir=work_dir)
        await safe_send({"type": "task_list", "data": tasks})
        return

    elif action == "rollback_task":
        target_task_id = data.get("target_task_id") or task_id
        if not target_task_id:
            await safe_send({"type": "system_msg", "content": "❌ 未指定要回退的任务 ID"})
            return

        steps = data.get("steps", 0)
        if steps and steps > 0:
            logger.info(f"⏪ 执行任务步骤回退！task={target_task_id}, steps={steps}")
            result = sm.rollback_step_session(target_task_id, steps=steps)
        else:
            logger.info(f"⏪ 执行任务级物理回退！task={target_task_id}")
            result = sm.rollback_session(target_task_id)

        if result.get("success") or result.get("status") == "success":
            reverted_files = result.get("reverted_files", [])
            changed_files_raw = result.get("changed_files_raw", "")
            stat_summary = result.get("stat_summary", "")
            detailed_diff = result.get("detailed_diff", "")
            commits_being_reverted = result.get("commits_being_reverted", "")
            untracked_files = result.get("untracked_files", "")

            diff_audit_lines = []
            if commits_being_reverted:
                diff_audit_lines.append(f"📝 撤销的提交:\n{commits_being_reverted}")
            if reverted_files:
                diff_audit_lines.append("📂 撤销的文件变更:")
                for f in reverted_files:
                    diff_audit_lines.append(f"  {f['icon']} {f['status_label']}  {f['file']}")
            elif changed_files_raw:
                diff_audit_lines.append(f"📂 撤销的文件变更:\n{changed_files_raw}")
            else:
                diff_audit_lines.append("📂 没有检测到物理文件的变更，系统仅回退了 Agent 的对话记忆")
            if untracked_files:
                diff_audit_lines.append(f"🗑️ 清理的未追踪文件:\n{untracked_files}")
            if stat_summary:
                diff_audit_lines.append(f"📊 变更统计:\n{stat_summary}")

            diff_audit = "\n".join(diff_audit_lines)

            if steps and steps > 0:
                await safe_send({"type": "refresh_tree"})
                await safe_send({
                    "type": "task_step_rolled_back",
                    "task_id": target_task_id,
                    "steps_rolled_back": result.get("steps_rolled_back", steps),
                    "reverted_files": reverted_files,
                    "diff_audit": diff_audit,
                    "detailed_diff": detailed_diff,
                })
                try:
                    from rewind_system import get_rewind_system
                    rewind = get_rewind_system(user_id=user_id, session_id=target_task_id)
                    remaining_cps = rewind.list_checkpoints(target_task_id)
                    await safe_send({
                        "type": "checkpoints_updated",
                        "task_id": target_task_id,
                        "checkpoints": remaining_cps,
                    })
                except Exception:
                    pass
                await safe_send({
                    "type": "system_msg",
                    "content": f"⏪ 任务「{target_task_id}」已回退 {result.get('steps_rolled_back', steps)} 步\n{diff_audit}",
                })
            else:
                messages_before = result.get("messages_before", [])
                logger.info(f"⏪ 物理回退成功: {result.get('summary', target_task_id)}")
                await safe_send({"type": "refresh_tree"})
                await safe_send({
                    "type": "system_msg",
                    "content": f"✅ 任务「{result.get('summary', target_task_id)}」已物理回退\n{diff_audit}",
                })
                await safe_send({
                    "type": "task_rolled_back",
                    "task_id": target_task_id,
                    "reverted_files": reverted_files,
                    "diff_audit": diff_audit,
                    "detailed_diff": detailed_diff,
                })
        else:
            await safe_send({
                "type": "system_msg",
                "content": f"❌ 回退失败: {result.get('error', result.get('message', '未知错误'))}",
            })
        return

    elif action == "preview_rollback":
        target_task_id = data.get("target_task_id") or task_id
        if not target_task_id:
            await safe_send({"type": "system_msg", "content": "❌ 未指定要预览回退的任务 ID"})
            return

        steps = data.get("steps", 1)
        to_turn = data.get("to_turn")

        session = sm.get_session(target_task_id)
        if not session:
            await safe_send({"type": "system_msg", "content": f"❌ 任务 {target_task_id} 不存在"})
            return

        work_dir = session.worktree_dir or session.work_dir

        from rewind_system import get_rewind_system
        rewind = get_rewind_system(user_id=user_id, session_id=target_task_id)
        preview = rewind.preview_rollback(
            session_id=target_task_id,
            steps=steps,
            to_turn=to_turn,
            work_dir=work_dir,
        )

        if preview.get("success"):
            await safe_send({
                "type": "rollback_preview",
                "task_id": target_task_id,
                "target_turn": preview.get("target_turn", 0),
                "target_description": preview.get("target_description", ""),
                "target_git_commit": preview.get("target_git_commit", ""),
                "removed_turns": preview.get("removed_turns", []),
                "removed_descriptions": preview.get("removed_descriptions", []),
                "reverted_files": preview.get("reverted_files", []),
                "stat_summary": preview.get("stat_summary", ""),
                "detailed_diff": preview.get("detailed_diff", ""),
                "diff_report": preview.get("diff_report", ""),
                "diff_lines": preview.get("diff_lines", []),
                "commits_being_reverted": preview.get("commits_being_reverted", ""),
            })
        else:
            await safe_send({
                "type": "system_msg",
                "content": f"❌ 预览失败: {preview.get('error', '未知错误')}",
            })
        return

    elif action == "view_checkpoint":
        target_task_id = data.get("target_task_id") or task_id
        view_turn = data.get("turn")
        if not target_task_id or view_turn is None:
            await safe_send({"type": "system_msg", "content": "❌ 缺少参数: target_task_id 或 turn"})
            return

        session = sm.get_session(target_task_id)
        if not session:
            await safe_send({"type": "system_msg", "content": f"❌ 任务 {target_task_id} 不存在"})
            return

        work_dir = session.worktree_dir or session.work_dir

        from rewind_system import get_rewind_system
        rewind = get_rewind_system(user_id=user_id, session_id=target_task_id)
        view = rewind.view_checkpoint(
            session_id=target_task_id,
            turn=view_turn,
            work_dir=work_dir,
        )

        if view.get("success"):
            await safe_send({
                "type": "checkpoint_view",
                "task_id": target_task_id,
                "turn": view.get("turn", 0),
                "timestamp": view.get("timestamp", 0),
                "description": view.get("description", ""),
                "git_commit": view.get("git_commit", ""),
                "diff_stat": view.get("diff_stat", ""),
                "changed_files": view.get("changed_files", []),
                "detailed_diff": view.get("detailed_diff", ""),
                "diff_lines": view.get("diff_lines", []),
                "code_diff": view.get("code_diff", ""),
            })
        else:
            await safe_send({
                "type": "system_msg",
                "content": f"❌ 查看失败: {view.get('error', '未知错误')}",
            })
        return

    elif action == "stop_agent":
        session_id = task_id or "default"
        set_stop_flag(session_id, True)
        logger.info(f"🛑 用户请求停止 Agent: session={session_id}")
        await safe_send({
            "type": "system_msg",
            "content": "🛑 正在停止 Agent...",
        })
        return

    elif action == "switch_task":
        target_task_id = data.get("target_task_id") or task_id
        if not target_task_id:
            await safe_send({"type": "system_msg", "content": "❌ 未指定要切换的任务 ID"})
            return

        result = sm.switch_session(target_task_id)
        if result.get("success"):
            checkpoints = []
            try:
                from rewind_system import get_rewind_system
                rewind = get_rewind_system(user_id=user_id, session_id=target_task_id)
                checkpoints = rewind.list_checkpoints(target_task_id)
            except Exception:
                pass
            await safe_send({"type": "refresh_tree"})
            await safe_send({
                "type": "task_switched",
                "task_id": target_task_id,
                "summary": result.get("summary", ""),
                "work_dir": result.get("work_dir", ""),
                "checkpoints": checkpoints,
            })
            await safe_send({
                "type": "system_msg",
                "content": f"🔄 已切换到任务「{result.get('summary', target_task_id)}」",
            })
        else:
            await safe_send({
                "type": "system_msg",
                "content": f"❌ 切换失败: {result.get('error', '未知错误')}",
            })
        return

    elif action == "get_task_commits":
        target_task_id = data.get("target_task_id") or task_id
        if target_task_id:
            session = sm.get_session(target_task_id)
            if session:
                from sandbox_manager import get_sandbox
                sandbox = get_sandbox(session.work_dir)
                commits = sandbox.get_task_commits(target_task_id)
                await safe_send({"type": "task_commits", "task_id": target_task_id, "data": commits})
                return
        await safe_send({"type": "task_commits", "task_id": target_task_id, "data": []})
        return

    elif action == "list_checkpoints":
        from rewind_system import get_rewind_system
        target_task_id = data.get("target_task_id") or task_id or sm.current_task_id
        if not target_task_id:
            await safe_send({"type": "checkpoint_list", "data": []})
            return
        rm = get_rewind_system(user_id=user_id, session_id=target_task_id)
        rm.load_checkpoints(target_task_id)
        checkpoints = rm.list_checkpoints(target_task_id)
        await safe_send({"type": "checkpoint_list", "data": checkpoints})
        return

    elif action == "clear_checkpoints":
        from rewind_system import get_rewind_system
        target_task_id = data.get("target_task_id") or task_id or sm.current_task_id
        if not target_task_id:
            await safe_send({"type": "system_msg", "content": "❌ 未指定任务 ID"})
            return
        rm = get_rewind_system(user_id=user_id, session_id=target_task_id)
        rm.clear_checkpoints(target_task_id)
        await safe_send({"type": "system_msg", "content": f"🗑️ 任务 {target_task_id} 的检查点已清除"})
        return

    elif action == "merge_task":
        target_task_id = data.get("target_task_id") or task_id or sm.current_task_id
        force_merge = data.get("force", False)
        if not target_task_id:
            await safe_send({"type": "system_msg", "content": "❌ 未指定要合并的任务 ID"})
            return

        logger.info(f"🔀 尝试合并任务 {target_task_id} 到主干 (force={force_merge})")

        result = sm.merge_session(target_task_id, force=force_merge)

        if result.get("status") == "success":
            await safe_send({"type": "refresh_tree"})
            await safe_send({
                "type": "task_merged",
                "task_id": target_task_id,
                "message": result.get("message", ""),
            })
            await safe_send({
                "type": "system_msg",
                "content": f"✅ 任务「{target_task_id}」已成功合入主干！",
            })
        elif result.get("status") == "conflict":
            conflict_files = result.get("conflict_files", [])
            await safe_send({
                "type": "task_conflict",
                "task_id": target_task_id,
                "conflict_files": conflict_files,
                "message": result.get("message", ""),
            })
            await safe_send({
                "type": "system_msg",
                "content": f"⚠️ 任务「{target_task_id}」与主干冲突！冲突文件: {', '.join(conflict_files[:5])}",
            })
        else:
            await safe_send({
                "type": "system_msg",
                "content": f"❌ 合并失败: {result.get('message', '未知错误')}",
            })
        return

    elif action == "revert_merged_task":
        target_task_id = data.get("target_task_id") or task_id
        if not target_task_id:
            await safe_send({"type": "system_msg", "content": "❌ 未指定要撤销的任务 ID"})
            return

        logger.info(f"🚑 尝试 revert 已合并任务 {target_task_id}")

        result = sm.revert_merged_session(target_task_id)

        if result.get("status") == "success":
            await safe_send({"type": "refresh_tree"})
            await safe_send({
                "type": "task_reverted",
                "task_id": target_task_id,
                "message": result.get("message", ""),
            })
            await safe_send({
                "type": "system_msg",
                "content": f"🚑 任务「{target_task_id}」的影响已通过 revert 安全抵消",
            })
        else:
            await safe_send({
                "type": "system_msg",
                "content": f"❌ Revert 失败: {result.get('message', '未知错误')}",
            })
        return

    elif action == "list_mcp_services":
        try:
            from mcp_client import MCPClient, MCP_DYNAMIC_REGISTRY
            mcp = MCPClient()
            mcp.load_config()
            status_text = mcp.list_available_servers()
            await safe_send({"type": "mcp_services", "data": status_text})
        except Exception as e:
            await safe_send({"type": "mcp_services", "data": f"❌ 获取 MCP 服务列表失败: {e}"})
        return

    elif action == "delete_task":
        target_task_id = data.get("target_task_id") or task_id
        if not target_task_id:
            await safe_send({"type": "system_msg", "content": "❌ 未指定要删除的任务 ID"})
            return

        session = sm.get_session(target_task_id)
        if not session:
            await safe_send({"type": "system_msg", "content": f"❌ 任务 {target_task_id} 不存在"})
            return

        work_dir = session.work_dir
        is_passthrough = session.worktree_dir == session.work_dir
        try:
            if not is_passthrough:
                from sandbox_manager import get_sandbox
                sandbox = get_sandbox(work_dir)
                sandbox.remove_task_workspace(target_task_id)
        except Exception as e:
            logger.warning(f"删除 worktree 失败: {e}")

        try:
            from task_registry import get_task_registry
            registry = get_task_registry(user_id=user_id)
            registry.delete_task(target_task_id)
        except Exception as e:
            logger.warning(f"清理 TaskRegistry 失败: {e}")

        sm.delete_session(target_task_id)

        if sm.current_task_id == target_task_id:
            sm.current_task_id = None

        logger.info(f"🗑️ 任务 {target_task_id} 已删除")
        await safe_send({"type": "task_deleted", "task_id": target_task_id})
        await safe_send({"type": "system_msg", "content": f"🗑️ 任务「{session.summary[:30]}」已删除"})
        return

    else:
        await safe_send({
            "type": "system_msg",
            "content": f"❌ 未知系统指令: {action}",
        })
        return


async def _shielded_career_analysis(user_id: int, task_id: str, work_dir: str):
    """
    后台护盾协程：无论 WebSocket 是否断开，都独立完成职业档案分析并推送 Java 中台。
    使用 career_analyzer 的 LLM 深度分析 + 关键词 fallback 双保险机制。
    绝对安全：任何异常只打日志，不影响主引擎。
    """
    await asyncio.sleep(2)

    try:
        if not user_id or user_id <= 0:
            logger.debug(f"🛡️ 护盾跳过: user_id={user_id} 无效")
            return

        if not task_id:
            logger.debug("🛡️ 护盾跳过: task_id 为空")
            return

        logger.info(f"🛡️ 护盾开始职业分析: user={user_id}, task={task_id}")

        from task_manager import get_session_manager
        sm = get_session_manager(user_id=user_id)
        session = sm.get_session(task_id)

        session_messages = []
        if session:
            session_messages = (session.messages_before or []) + (session.messages or [])

        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "protobuf-rpc-bridge", "python"))
        from career_analyzer import analyze_career

        result = await analyze_career(
            user_id=user_id,
            work_dir=work_dir,
            session_messages=session_messages,
        )

        if result and (result.get("skills") or result.get("resume_highlight")):
            from rpc_entry import report_career_advice
            report_career_advice(
                user_id=user_id,
                extracted_skills=result.get("skills", []),
                resume_highlight=result.get("resume_highlight", ""),
                next_suggestion=result.get("next_suggestion", ""),
            )
            logger.info(
                f"🛡️ 护盾职业分析完成并推送 Java: user={user_id}, "
                f"skills={result.get('skills', [])}, highlight_len={len(result.get('resume_highlight', ''))}"
            )
        else:
            logger.info(f"🛡️ 护盾分析完成但无有效数据可推送: user={user_id}, task={task_id}")

    except Exception as e:
        logger.error(f"🛡️ 护盾职业分析失败 (非致命): {e}")


# ============================================================================
# WebSocket 端点 - /ws/coding
# ============================================================================

@app.websocket("/ws/coding")
@app.websocket("/ws/simple-ide")
async def websocket_coding(websocket: WebSocket, user_id: int = 0):
    """
    WebSocket 双向通信 - Agent 的"神经系统"

    协议:
      客户端发送: {"task": "写一个二叉树", "model": "gpt-4o", ...}
      服务端推送: {"type": "status", "data": "Agent 正在思考..."}
                 {"type": "tool_start", "tool_name": "bash", "args": {...}}
                 {"type": "tool_end", "tool_name": "bash", "result": "...", "is_error": false}
                 {"type": "finish", "data": "最终结果"}

    Qt/C++ 对接示例:
        void CodingLabWindow::onTextMessageReceived(QString message) {
            QJsonObject obj = QJsonDocument::fromJson(message.toUtf8()).object();
            QString type = obj["type"].toString();

            if (type == "tool_start") {
                // 显示: Agent 正在使用 bash 工具...
                QString toolName = obj["tool_name"].toString();
                ui->statusLabel->setText("正在执行: " + toolName);
            }
            else if (type == "tool_end") {
                // 显示工具执行结果
                bool isError = obj["is_error"].toBool();
                QString result = obj["result"].toString();
                if (isError) {
                    appendTerminalLog("[ERROR] " + result);
                } else {
                    appendTerminalLog(result);
                }
            }
            else if (type == "finish") {
                ui->statusLabel->setText("任务完成");
            }
        }
    """
    await websocket.accept()
    
    ws_connected = True
    effective_user_id = user_id if user_id else 0
    has_analyzed = False

    async def safe_trigger_analysis(uid: int, tid: str, wdir: str):
        nonlocal has_analyzed
        if has_analyzed:
            return
        has_analyzed = True
        if not uid or uid <= 0 or not tid:
            return
        logger.info(f"🛡️ 启动全量代码增量分析，用户: {uid}, 任务: {tid}")
        try:
            asyncio.create_task(
                _shielded_career_analysis(user_id=uid, task_id=tid, work_dir=wdir)
            )
        except Exception as shield_err:
            logger.error(f"🛡️ 护盾启动失败 (非致命): {shield_err}")

    async def safe_send(data: dict):
        nonlocal ws_connected
        if not ws_connected:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception:
            ws_connected = False
            return False
    
    client_message_queue = asyncio.Queue()
    
    async def receive_client_messages():
        nonlocal ws_connected
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    if data.get("type") == "system_command":
                        try:
                            await _handle_system_command(websocket, data, safe_send)
                        except Exception as e:
                            logger.error(f"❌ 系统命令处理异常: {e}")
                            await safe_send({"type": "system_msg", "content": f"❌ 系统命令执行失败: {str(e)[:100]}"})
                        continue
                    logger.info(f"📨 收到客户端消息: type={data.get('type')}, task={str(data.get('task', ''))[:40]}")
                    await client_message_queue.put(data)
                except json.JSONDecodeError:
                    logger.warning(f"📨 收到无效 JSON: {raw[:100]}")
        except Exception as e:
            e_str = str(e)
            if "1000" in e_str or "1001" in e_str or "1005" in e_str or "1012" in e_str:
                logger.info(f"📨 WebSocket 正常关闭: {e}")
            else:
                logger.error(f"❌ receive_client_messages 异常退出: {e}")
            ws_connected = False
        finally:
            await client_message_queue.put(None)

    receive_task = asyncio.create_task(receive_client_messages())
    
    task_id = None

    try:
        while ws_connected:
            try:
                data = await asyncio.wait_for(client_message_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            if data is None:
                logger.warning("📨 收到哨兵值，接收任务已退出")
                break

            if data.get("type") == "system_command":
                try:
                    await _handle_system_command(websocket, data, safe_send)
                except Exception as e:
                    logger.error(f"❌ 系统命令处理异常: {e}")
                    await safe_send({"type": "system_msg", "content": f"❌ 系统命令执行失败: {str(e)[:100]}"})
                continue

            if data.get("type") == "user_answer":
                continue

            if data.get("type") == "command_confirm":
                continue

            msg_type = data.get("type", "")
            user_input = data.get("task") or data.get("prompt") or data.get("content", "")
            images = data.get("images") or []
            if images and not isinstance(images, list):
                images = [images]
            skills = data.get("skills") or []
            if skills and not isinstance(skills, list):
                skills = [skills]
            if not user_input:
                await safe_send({"type": "error", "data": "task/prompt 不能为空"})
                continue

            logger.info(f"📨 开始处理消息: type={msg_type}, input={user_input[:50]}")

            work_dir = data.get("work_dir", SANDBOX_DIR)
            max_turns = data.get("max_turns", MAX_TURNS)
            api_key = data.get("api_key") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            model = data.get("model")
            base_url = data.get("base_url") or os.environ.get("OPENAI_BASE_URL")
            provider = data.get("provider", API_PROVIDER)

            if not model:
                model = DEFAULT_MODEL_ANTHROPIC if provider == "anthropic" else DEFAULT_MODEL_OPENAI

            if base_url and not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

            os.makedirs(work_dir, exist_ok=True)

            original_work_dir = work_dir

            use_worktree = True

            from task_manager import get_session_manager
            sm = get_session_manager(user_id=effective_user_id)
            task_id = data.get("task_id")

            initial_messages = None
            start_turn = 1

            try:
                if msg_type == "chat_new_task":
                    base_task_id = data.get("base_task_id", "")
                    session = sm.get_or_create_session(
                        task_id=None,
                        first_prompt=user_input,
                        work_dir=work_dir,
                        existing_messages=None,
                        base_task_id=base_task_id,
                        use_worktree=use_worktree,
                    )
                    task_id = session.id
                    initial_messages = None
                    work_dir = session.worktree_dir or work_dir
                    mode_label = "worktree" if use_worktree else "直通"
                    logger.info(f"🆕 新任务 {task_id}: {session.summary[:50]} ({mode_label}: {work_dir})" + (f" 基于 {base_task_id}" if base_task_id else ""))

                elif msg_type == "chat_continue" and task_id:
                    session = sm.get_or_create_session(
                        task_id=task_id,
                        first_prompt=user_input,
                        work_dir=work_dir,
                        use_worktree=use_worktree,
                    )
                    if session.messages:
                        initial_messages = session.messages_before + session.messages
                    else:
                        initial_messages = session.messages_before or None
                    start_turn = 1
                    work_dir = session.worktree_dir or work_dir
                    logger.info(f"🔄 继续任务 {task_id}: {len(session.messages)} 条任务消息, start_turn={start_turn}")

                    if initial_messages and user_input:
                        last_msg = initial_messages[-1] if initial_messages else None
                        if last_msg and last_msg.get("role") == "assistant" and last_msg.get("tool_calls"):
                            for tc in last_msg["tool_calls"]:
                                fn = tc.get("function", tc) if isinstance(tc.get("function"), dict) else {}
                                tc_name = fn.get("name", "") if isinstance(fn, dict) else ""
                                if tc_name == "ask_user":
                                    tc_id = tc.get("id", "")
                                    has_response = any(
                                        m.get("role") == "tool" and m.get("tool_call_id") == tc_id
                                        for m in initial_messages
                                    )
                                    if not has_response:
                                        logger.info(f"🔧 检测到未配对的 ask_user tool_call (id={tc_id}), 注入用户回答作为 tool response")
                                        initial_messages.append({
                                            "role": "tool",
                                            "tool_call_id": tc_id,
                                            "name": "ask_user",
                                            "content": user_input,
                                        })
                                        user_input = ""
                                        break

                elif task_id:
                    session = sm.get_or_create_session(
                        task_id=task_id,
                        first_prompt=user_input,
                        work_dir=work_dir,
                        use_worktree=use_worktree,
                    )
                    if session.messages:
                        initial_messages = session.messages_before + session.messages
                    else:
                        initial_messages = session.messages_before or None
                    start_turn = 1
                    work_dir = session.worktree_dir or work_dir

                    if initial_messages and user_input:
                        last_msg = initial_messages[-1] if initial_messages else None
                        if last_msg and last_msg.get("role") == "assistant" and last_msg.get("tool_calls"):
                            for tc in last_msg["tool_calls"]:
                                fn = tc.get("function", tc) if isinstance(tc.get("function"), dict) else {}
                                tc_name = fn.get("name", "") if isinstance(fn, dict) else ""
                                if tc_name == "ask_user":
                                    tc_id = tc.get("id", "")
                                    has_response = any(
                                        m.get("role") == "tool" and m.get("tool_call_id") == tc_id
                                        for m in initial_messages
                                    )
                                    if not has_response:
                                        logger.info(f"🔧 检测到未配对的 ask_user tool_call (id={tc_id}), 注入用户回答作为 tool response")
                                        initial_messages.append({
                                            "role": "tool",
                                            "tool_call_id": tc_id,
                                            "name": "ask_user",
                                            "content": user_input,
                                        })
                                        user_input = ""
                                        break
                else:
                    session = sm.get_or_create_session(
                        task_id=None,
                        first_prompt=user_input,
                        work_dir=work_dir,
                        use_worktree=use_worktree,
                    )
                    task_id = session.id
                    initial_messages = None
                    work_dir = session.worktree_dir or work_dir
            except Exception as e:
                logger.error(f"❌ 创建/获取会话失败: {e}")
                await safe_send({"type": "error", "data": f"创建任务失败: {str(e)}"})
                task_id = None
                continue

            auto_approve = data.get("auto_approve", False)
            use_swarm = data.get("use_swarm", False)
            enable_routing = data.get("enable_routing", False)
            msg_user_id = data.get("user_id") or 0
            try:
                msg_user_id = int(msg_user_id)
            except (ValueError, TypeError):
                msg_user_id = 0
            effective_user_id = user_id or msg_user_id or 0
            if not effective_user_id:
                effective_user_id = 1
                logger.warning(f"WebSocket message missing user_id, falling back to 1")

            agent_params = {
                "user_input": user_input,
                "work_dir": work_dir,
                "main_repo_dir": original_work_dir,
                "max_turns": max_turns,
                "api_key": api_key,
                "model": model,
                "base_url": base_url,
                "provider": provider,
                "task_id": task_id,
                "initial_messages": initial_messages,
                "start_turn": start_turn,
                "auto_approve": auto_approve,
                "use_swarm": use_swarm,
                "user_id": effective_user_id,
                "enable_routing": enable_routing,
                "images": images,
                "skills": skills,
            }

            engine_name = "🧠 Swarm (多智能体)" if use_swarm else "⚡ 单体 Agent"
            logger.info(f"{engine_name} 引擎启动: task={task_id}, model={model}, work_dir={work_dir}")

            agent_needs_restart = True
            while agent_needs_restart:
                agent_needs_restart = False
                async for event in _run_agent_async(**agent_params):
                    if event.get("type") == "task_started":
                        event["work_dir"] = work_dir
                        try:
                            from rewind_system import get_rewind_system
                            rewind = get_rewind_system(user_id=effective_user_id, session_id=event.get("task_id", task_id or ""))
                            cps = rewind.list_checkpoints(event.get("task_id", task_id or ""))
                            event["checkpoints"] = cps
                        except Exception:
                            pass

                    if event.get("type") != "ask_user":
                        if not await safe_send(event):
                            return

                    if event.get("type") == "tool_end" and not event.get("is_error"):
                        tool_name = event.get("tool_name", "")
                        if tool_name and ("file_edit" in tool_name or "file_write" in tool_name or "bash" in tool_name):
                            try:
                                from rewind_system import get_rewind_system
                                rewind = get_rewind_system(user_id=effective_user_id, session_id=task_id or "")
                                cps = rewind.list_checkpoints(task_id or "")
                                if cps:
                                    await safe_send({
                                        "type": "checkpoints_updated",
                                        "task_id": task_id,
                                        "checkpoints": cps,
                                    })
                            except Exception:
                                pass

                    if event.get("type") == "artifacts_ready":
                        artifact_data = event.get("data", {})
                        execution_env = artifact_data.get("execution_env", "native")
                        if execution_env == "webcontainer":
                            await safe_send({
                                "type": "webcontainer_artifacts",
                                "task_id": task_id,
                                "execution_env": execution_env,
                                "vfs": artifact_data.get("vfs", {}),
                                "file_count": artifact_data.get("file_count", 0),
                                "total_size_bytes": artifact_data.get("total_size_bytes", 0),
                            })
                            logger.info(
                                f"🌐 WebContainer 产物已推送: task={task_id}, "
                                f"files={artifact_data.get('file_count', 0)}"
                            )
                        else:
                            await safe_send({
                                "type": "artifacts_ready",
                                "task_id": task_id,
                                "execution_env": execution_env,
                                "file_count": artifact_data.get("file_count", 0),
                                "total_size_bytes": artifact_data.get("total_size_bytes", 0),
                            })

                    if event.get("type") == "ask_user":
                        event_data = event.get("data", {})
                        question_id = event_data.get("question_id", "")
                        tool_call_id = event_data.get("tool_call_id", "")
                        ask_task_id = event_data.get("task_id", task_id or "")
                        ask_provider = event_data.get("provider", "openai")

                        if not await safe_send(event):
                            return

                        while True:
                            try:
                                msg = await asyncio.wait_for(client_message_queue.get(), timeout=2)
                            except asyncio.TimeoutError:
                                if check_stop_flag(task_id or "default"):
                                    logger.info(f"🛑 ask_user 等待期间检测到停止信号，立即终止")
                                    await safe_send({"type": "agent_status", "status": "IDLE"})
                                    await safe_send({"type": "stopped", "data": "用户已停止 Agent 执行"})
                                    return
                                continue

                            if msg is None:
                                return

                            if msg.get("type") == "system_command" and msg.get("action") == "stop_agent":
                                logger.info(f"🛑 用户在 ask_user 等待期间请求停止 Agent")
                                await safe_send({"type": "agent_status", "status": "IDLE"})
                                await safe_send({"type": "stopped", "data": "用户已停止 Agent 执行"})
                                return

                            if msg.get("type") == "user_answer" and msg.get("question_id") == question_id:
                                user_answer = msg.get("answer", "")

                                if ask_task_id:
                                    try:
                                        from task_manager import get_task_manager
                                        tm = get_task_manager(user_id=effective_user_id)
                                        session = tm.get_session(ask_task_id)
                                        if session and session.messages:
                                            history = session.messages_before + session.messages if session.messages_before else session.messages
                                            history.append({
                                                "role": "tool",
                                                "tool_call_id": tool_call_id,
                                                "name": "ask_user",
                                                "content": user_answer,
                                            })
                                            tm.update_session_messages(
                                                task_id=ask_task_id,
                                                messages=session.messages,
                                                current_turn=session.current_turn,
                                            )
                                            agent_params["initial_messages"] = history
                                            agent_params["start_turn"] = 1
                                            agent_params["user_input"] = ""
                                    except Exception as e:
                                        logger.error(f"注入 ask_user 工具回复失败: {e}")
                                        agent_params["user_input"] = f"用户回答: {user_answer}\n请继续执行任务。"
                                else:
                                    agent_params["user_input"] = f"用户回答: {user_answer}\n请继续执行任务。"

                                break

                        agent_needs_restart = True
                        break

                    if event.get("type") == "command_confirmation":
                        event_data = event.get("data", {})
                        confirm_id = str(uuid.uuid4())[:8]
                        event_data["confirmation_id"] = confirm_id

                        saved_messages = event_data.pop("messages", None)
                        saved_turn = event_data.pop("turn", 1)

                        if not await safe_send(event):
                            return

                        while True:
                            try:
                                msg = await asyncio.wait_for(client_message_queue.get(), timeout=300)
                                if msg is None:
                                    return

                                if msg.get("type") == "system_command" and msg.get("action") == "stop_agent":
                                    logger.info(f"🛑 用户在 command_confirmation 等待期间请求停止 Agent")
                                    await safe_send({"type": "agent_status", "status": "IDLE"})
                                    await safe_send({"type": "stopped", "data": "用户已停止 Agent 执行"})
                                    return

                                if msg.get("type") == "command_confirm" and msg.get("confirmation_id") == confirm_id:
                                    from bash_executor import execute_bash
                                    command = event_data.get("command", "")

                                    if msg.get("approved"):
                                        result = execute_bash(command, work_dir=work_dir, allow_warnings=True)
                                        if result.blocked:
                                            output = f"命令被拦截: {result.block_reason}"
                                            is_error = True
                                        else:
                                            output = result.stdout or ""
                                            if result.stderr:
                                                output += f"\n[stderr]\n{result.stderr}"
                                            is_error = result.exit_code != 0

                                            if is_error and result.stderr:
                                                from bash_executor import parse_compiler_errors
                                                diagnostics = parse_compiler_errors(result.stderr, work_dir)
                                                if diagnostics:
                                                    await safe_send({
                                                        "type": "diagnostics",
                                                        "diagnostics": diagnostics,
                                                    })
                                    else:
                                        output = "用户拒绝执行此命令"
                                        is_error = True

                                    await safe_send({
                                        "type": "tool_end",
                                        "tool_name": "bash",
                                        "result": output,
                                        "is_error": is_error
                                    })

                                    if saved_messages:
                                        tool_call_id = event_data.get("tool_call_id", "")
                                        saved_messages.append({
                                            "role": "tool",
                                            "tool_call_id": tool_call_id,
                                            "content": output,
                                        })
                                        agent_params["initial_messages"] = saved_messages
                                        agent_params["start_turn"] = saved_turn
                                        agent_params["user_input"] = ""
                                    else:
                                        agent_params["user_input"] = f"命令执行结果:\n```\n{output}\n```\n请继续执行任务。"
                                    break
                            except asyncio.TimeoutError:
                                await safe_send({"type": "error", "data": "等待用户确认超时"})
                                return

                        agent_needs_restart = True
                        break

                    await asyncio.sleep(0.01)

            if task_id:
                logger.info(f"💾 任务 {task_id} Agent 循环结束 (消息已由 run_agent 内部每轮保存)")
                await safe_trigger_analysis(effective_user_id, task_id, work_dir)

            task_id = None

    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开连接")
        if task_id:
            await safe_trigger_analysis(effective_user_id, task_id, work_dir)
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
        await safe_send({"type": "error", "data": str(e)})
    finally:
        receive_task.cancel()
        from ask_user_tool import cancel_all_questions
        cancel_all_questions()
        if task_id:
            logger.info(f"💾 任务 {task_id} Agent 循环结束 (finally, 消息已由 run_agent 内部保存)")
            await safe_trigger_analysis(effective_user_id, task_id, work_dir)
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# WebSocket 端点 - 长连接多任务模式
# ============================================================================

@app.websocket("/ws/coding/persistent")
@app.websocket("/ws/simple-ide/persistent")
async def websocket_coding_persistent(websocket: WebSocket):
    """
    持久 WebSocket 连接 - 支持多任务切换

    协议:
      客户端发送: {"action": "run", "task": "写一个二叉树", ...}
      客户端发送: {"action": "switch_task", "task_id": "xxx"}
      客户端发送: {"action": "create_task", "task_name": "xxx", "project_path": "xxx"}
      客户端发送: {"action": "list_tasks", "project_path": "xxx"}
      客户端发送: {"action": "ping"}
      服务端推送: {"type": "pong"}
      服务端推送: {"type": "task_switched", ...}
    """
    await websocket.accept()
    
    ws_connected = True
    
    async def safe_send(data: dict):
        nonlocal ws_connected
        if not ws_connected:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception:
            ws_connected = False
            return False
    
    from task_manager import get_task_manager
    from rewind_system import get_rewind_system
    persistent_user_id = 0
    task_manager = get_task_manager(user_id=persistent_user_id or 1)
    rewind_system = get_rewind_system(user_id=1, session_id="persistent")
    
    current_messages = []
    current_active_files = set()
    current_blackboard = {}
    current_turn = 0
    
    try:
        while ws_connected:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await safe_send({"type": "error", "data": "无效的 JSON 格式"})
                continue

            action = data.get("action", "")

            if data.get("type") == "system_command":
                await _handle_system_command(websocket, data, safe_send)
                continue

            if action == "ping":
                await safe_send({"type": "pong"})
                continue

            if action == "close":
                break

            if action == "list_tasks":
                project_path = data.get("project_path", "")
                tasks = task_manager.list_tasks(project_path)
                await safe_send({"type": "task_list", "tasks": tasks})
                continue

            if action == "create_task":
                task_id = data.get("task_id") or str(uuid.uuid4())[:8]
                task_name = data.get("task_name", "新任务")
                project_path = data.get("project_path", SANDBOX_DIR)
                task_data = task_manager.create_task(task_id, task_name, project_path)
                await safe_send({"type": "task_created", "task_data": task_data})
                continue

            if action == "switch_task":
                new_task_id = data.get("task_id", "")
                work_dir = data.get("work_dir", SANDBOX_DIR)
                
                if not new_task_id:
                    await safe_send({"type": "error", "data": "task_id 不能为空"})
                    continue
                
                switch_result = task_manager.switch_task(
                    new_task_id=new_task_id,
                    current_messages=current_messages,
                    current_active_files=current_active_files,
                    current_blackboard=current_blackboard,
                    current_turn=current_turn,
                    work_dir=work_dir,
                    rewind_system=rewind_system,
                )
                
                if switch_result["success"]:
                    new_task_data = switch_result["task_data"]
                    current_messages = new_task_data.get("messages", [])
                    current_active_files = set(new_task_data.get("active_files", []))
                    current_blackboard = new_task_data.get("blackboard", {})
                    current_turn = new_task_data.get("current_turn", 0)
                    
                    await safe_send({
                        "type": "task_switched",
                        "data": {
                            "task_id": new_task_id,
                            "task_name": new_task_data.get("task_name", ""),
                            "message": switch_result["message"],
                            "restored_files": switch_result["restored_files"],
                            "messages_count": len(current_messages),
                            "current_turn": current_turn,
                        },
                    })
                    await safe_send({"type": "refresh_tree"})
                else:
                    await safe_send({"type": "error", "data": switch_result.get("message", "切换任务失败")})
                continue

            if action == "run":
                user_input = data.get("task") or data.get("prompt") or ""
                if not user_input:
                    await safe_send({"type": "error", "data": "task/prompt 不能为空"})
                    continue

                work_dir = data.get("work_dir", SANDBOX_DIR)
                max_turns = data.get("max_turns", MAX_TURNS)
                api_key = data.get("api_key") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
                model = data.get("model")
                base_url = data.get("base_url") or os.environ.get("OPENAI_BASE_URL")
                provider = data.get("provider", API_PROVIDER)

                if not model:
                    model = DEFAULT_MODEL_ANTHROPIC if provider == "anthropic" else DEFAULT_MODEL_OPENAI

                if base_url and not base_url.endswith("/v1"):
                    base_url = base_url.rstrip("/") + "/v1"

                os.makedirs(work_dir, exist_ok=True)

                task_id = data.get("task_id") or task_manager.current_task_id
                if task_id and not task_manager.current_task_id:
                    task_manager.current_task_id = task_id

                use_swarm = data.get("use_swarm", False)
                engine_name = "🧠 Swarm (多智能体)" if use_swarm else "⚡ 单体 Agent"
                logger.info(f"{engine_name} [Persistent] 引擎启动: task={task_id}, model={model}")

                async for event in _run_agent_async(
                    user_input=user_input,
                    work_dir=work_dir,
                    max_turns=max_turns,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    provider=provider,
                    task_id=task_id,
                    use_swarm=use_swarm,
                ):
                    if not await safe_send(event):
                        break
                    
                    if event.get("type") == "status":
                        import re
                        m = re.search(r'第 (\d+)/', event.get("data", ""))
                        if m:
                            current_turn = int(m.group(1))
                    
                    if event.get("type") == "finish":
                        if task_manager.current_task_id:
                            task_manager.update_session_messages(
                                task_id=task_manager.current_task_id,
                                messages=current_messages,
                                current_turn=current_turn,
                            )
                    
                    await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        logger.info("持久 WebSocket 客户端断开连接")
    except Exception as e:
        logger.error(f"持久 WebSocket 异常: {e}")
        await safe_send({"type": "error", "data": str(e)})
    finally:
        if task_manager.current_task_id:
            task_manager.update_session_messages(
                task_id=task_manager.current_task_id,
                messages=current_messages,
                current_turn=current_turn,
            )
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# REST API 端点 - 同步模式
# ============================================================================

@app.post("/api/v1/execute")
async def execute_sync(request: ExecuteRequest):
    """
    同步执行模式 - 等待 Agent 完成后返回最终结果

    适用于不需要实时流式推送的场景（如 CI/CD、批量任务）
    """
    work_dir = request.work_dir or SANDBOX_DIR
    provider = request.provider or API_PROVIDER
    model = request.model or (DEFAULT_MODEL_ANTHROPIC if provider == "anthropic" else DEFAULT_MODEL_OPENAI)
    api_key = request.api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    base_url = request.base_url or os.environ.get("OPENAI_BASE_URL")

    # 确保 base_url 有 /v1 后缀（通义千问兼容模式需要）
    if base_url and not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    os.makedirs(work_dir, exist_ok=True)

    final_result = None
    all_events = []

    async for event in _run_agent_async(
        user_input=request.prompt,
        work_dir=work_dir,
        max_turns=request.max_turns,
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider,
    ):
        all_events.append(event)
        if event.get("type") in ("finish", "error"):
            final_result = event

    if final_result is None:
        return {"success": False, "message": "Agent 未产生最终结果", "events": all_events}

    return {
        "success": final_result.get("type") == "finish",
        "message": final_result.get("data", ""),
        "events": all_events,
    }


# ============================================================================
# 文件管理 API
# ============================================================================

@app.get("/api/v1/files")
async def list_files(path: str = SANDBOX_DIR):
    """获取目录下的所有文件列表"""
    import os
    from pathlib import Path
    
    try:
        base_path = Path(path)
        if not base_path.exists():
            base_path.mkdir(parents=True, exist_ok=True)
            return {"files": []}
        
        files = []
        for root, dirs, filenames in os.walk(base_path):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, base_path)
                files.append(rel_path)
        
        return {"files": sorted(files)}
    except Exception as e:
        return {"files": [], "error": str(e)}


@app.get("/api/v1/browse")
async def browse_directory(path: str = "/"):
    """浏览文件系统，返回指定目录下的所有文件夹"""
    import os
    from pathlib import Path
    
    try:
        base_path = Path(path)
        if not base_path.exists():
            return {"folders": [], "error": f"路径不存在: {path}"}
        
        if not base_path.is_dir():
            return {"folders": [], "error": f"不是目录: {path}"}
        
        folders = []
        try:
            for item in base_path.iterdir():
                if item.is_dir():
                    try:
                        folders.append({
                            "name": item.name,
                            "path": str(item.absolute()),
                        })
                    except PermissionError:
                        continue
        except PermissionError:
            return {"folders": [], "error": f"无权限访问: {path}"}
        
        folders.sort(key=lambda x: x["name"].lower())
        return {"folders": folders, "current_path": str(base_path.absolute())}
    except Exception as e:
        return {"folders": [], "error": str(e)}


@app.get("/api/v1/file")
async def read_file_content(path: str):
    """读取文件内容"""
    import os
    
    try:
        if not os.path.exists(path):
            return {"error": "文件不存在"}
        
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        return {"content": content, "path": path}
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# 任务管理 API
# ============================================================================

@app.get("/api/v1/tasks")
async def list_tasks(project_path: str = "", user_id: int = 0):
    from task_manager import get_session_manager
    sm = get_session_manager(user_id=user_id)
    tasks = sm.list_sessions(work_dir=project_path)
    for t in tasks:
        if "task_id" in t:
            t["id"] = t["task_id"]
        if "created_at" in t:
            t["created_at_str"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t["created_at"]))
    return {"tasks": tasks}


@app.get("/api/v1/task-registry")
async def list_task_registry(work_dir: str = "", user_id: int = 0):
    if not user_id:
        user_id = 1
    from task_manager import get_session_manager
    sm = get_session_manager(user_id=user_id)
    tasks = sm.list_sessions(work_dir="")
    return {"tasks": tasks}


@app.post("/api/v1/tasks")
async def create_task(request: dict):
    from task_manager import get_task_manager
    user_id = request.get("user_id", 0)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 0
    tm = get_task_manager(user_id=user_id)
    task_id = request.get("task_id") or str(uuid.uuid4())[:8]
    project_path = request.get("project_path", SANDBOX_DIR)
    task_name = request.get("task_name", "新任务")
    return {"task_id": task_id, "task_name": task_name, "project_path": project_path}


@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: str, user_id: int = 0):
    from task_manager import get_task_manager
    tm = get_task_manager(user_id=user_id)
    session = tm.get_session(task_id)
    if not session:
        return {"error": "任务不存在"}
    return session.to_dict()


@app.get("/api/v1/tasks/{task_id}/messages")
async def get_task_messages(task_id: str, user_id: int = 0):
    from task_manager import get_task_manager
    tm = get_task_manager(user_id=user_id)
    session = tm.get_session(task_id)
    if not session:
        return {"messages": [], "count": 0}
    all_messages = (session.messages_before or []) + (session.messages or [])
    return {"messages": all_messages, "count": len(all_messages)}


@app.put("/api/v1/tasks/{task_id}/status")
async def update_task_status(task_id: str, request: dict):
    from task_manager import get_task_manager
    user_id = request.get("user_id", 0)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 0
    tm = get_task_manager(user_id=user_id)
    tm.set_session_status(task_id, request.get("status", "active"))
    session = tm.get_session(task_id)
    return {"task_id": task_id, "status": session.status if session else "unknown"}


@app.post("/api/v1/tasks/{task_id}/switch")
async def switch_task(task_id: str, request: dict):
    from task_manager import get_task_manager
    from rewind_system import get_rewind_system
    user_id = request.get("user_id", 0)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 0
    tm = get_task_manager(user_id=user_id)
    rewind_system = get_rewind_system(user_id=user_id, session_id=task_id)
    
    work_dir = request.get("work_dir", SANDBOX_DIR)
    
    current_messages = request.get("current_messages", [])
    current_active_files = request.get("current_active_files", [])
    current_blackboard = request.get("current_blackboard", {})
    current_turn = request.get("current_turn", 0)
    
    switch_result = tm.switch_task(
        new_task_id=task_id,
        current_messages=current_messages,
        current_active_files=set(current_active_files),
        current_blackboard=current_blackboard,
        current_turn=current_turn,
        work_dir=work_dir,
        rewind_system=rewind_system,
    )
    
    if switch_result["success"]:
        new_task_data = switch_result["task_data"]
        return {
            "success": True,
            "task_id": task_id,
            "task_name": new_task_data.get("task_name", ""),
            "message": switch_result["message"],
            "restored_files": switch_result["restored_files"],
            "messages": new_task_data.get("messages", []),
            "current_turn": new_task_data.get("current_turn", 0),
            "blackboard": new_task_data.get("blackboard", {}),
        }
    else:
        return {"success": False, "error": switch_result.get("message", "切换失败")}


# ============================================================================
# 健康检查
# ============================================================================

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(sandbox_dir=SANDBOX_DIR, api_provider=API_PROVIDER)


@app.get("/")
async def root():
    return {
        "name": "Eruitah 智能编程沙盒",
        "version": "4.0.0",
        "endpoints": {
            "ide": "/ide",
            "websocket": "/ws/coding",
            "websocket_persistent": "/ws/coding/persistent",
            "execute": "/api/v1/execute",
            "health": "/api/v1/health",
        },
    }


@app.get("/ide")
async def ide_page():
    from fastapi.responses import FileResponse
    vue_index = os.path.join(_vue_dist_dir_resolved, "index.html") if os.path.isdir(_vue_dist_dir_resolved) else ""
    if vue_index and os.path.isfile(vue_index):
        return FileResponse(
            vue_index,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
        )
    html_path = os.path.join(STATIC_DIR, "coding_lab.html")
    if os.path.isfile(html_path):
        return FileResponse(html_path, media_type="text/html")
    return {"error": "IDE page not found", "hint": "请确保 coding-agent-ui/dist 或 static/coding_lab.html 存在"}


@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    """
    交互式终端 WebSocket - 真正的 shell 体验
    
    协议:
      客户端发送: {"type": "input", "data": "ls\n"}
                 {"type": "resize", "cols": 120, "rows": 40}
      服务端推送: {"type": "output", "data": "file1\nfile2\n"}
    """
    from interactive_terminal import InteractiveTerminal
    
    await websocket.accept()
    
    ws_connected = True
    
    async def safe_send(data: dict):
        nonlocal ws_connected
        if not ws_connected:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception:
            ws_connected = False
            return False
    
    pty_session = None
    output_task = None
    
    async def read_output():
        nonlocal ws_connected
        while pty_session and pty_session.running and ws_connected:
            try:
                output = pty_session.read(timeout=0.05)
                if output:
                    if not await safe_send({"type": "output", "data": output}):
                        break
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"读取 PTY 输出失败: {e}")
                break
    
    try:
        data = await websocket.receive_json()
        
        if data.get("type") == "start":
            work_dir = data.get("work_dir", SANDBOX_DIR)
            cols = data.get("cols", 80)
            rows = data.get("rows", 24)
            shell = data.get("shell")
            
            pty_session = InteractiveTerminal(
                work_dir=work_dir,
                shell=shell,
                cols=cols,
                rows=rows
            )
            
            if pty_session.start():
                await safe_send({
                    "type": "started",
                    "data": {
                        "pid": pty_session.pid,
                        "shell": pty_session.shell,
                        "cwd": pty_session.work_dir
                    }
                })
                output_task = asyncio.create_task(read_output())
            else:
                await safe_send({"type": "error", "data": "启动终端失败"})
                return
        
        while ws_connected:
            try:
                data = await websocket.receive_json()
                
                if data.get("type") == "input":
                    input_data = data.get("data", "")
                    if pty_session and input_data:
                        pty_session.write(input_data)
                
                elif data.get("type") == "resize":
                    cols = data.get("cols", 80)
                    rows = data.get("rows", 24)
                    if pty_session:
                        pty_session.resize(cols, rows)
                
            except Exception as e:
                logger.error(f"处理终端消息失败: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info("交互式终端 WebSocket 断开")
    except Exception as e:
        logger.error(f"交互式终端异常: {e}")
    finally:
        ws_connected = False
        if output_task:
            output_task.cancel()
        if pty_session:
            pty_session.stop()
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# 入口
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # 启动命令:
    #   python3 main.py
    #
    # 或:
    #   uvicorn main:app --host 0.0.0.0 --port 8001 --reload
    #
    # 环境变量:
    #   export ERUITAH_SANDBOX_DIR=/tmp/eruitah-sandbox
    #   export ERUITAH_API_PROVIDER=openai
    #   export OPENAI_API_KEY=sk-xxx

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
