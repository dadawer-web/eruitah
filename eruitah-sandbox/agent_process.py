"""
Agent Subprocess Manager - 进程级沙盒执行引擎

架构:
  ┌──────────────────┐  asyncio.Queue  ┌──────────────┐  multiprocessing.Queue  ┌──────────────────┐
  │  WebSocket (async) │ ◄──────────── │  Bridge 线程  │ ◄──────────────────── │  Agent 子进程     │
  │  主进程 - 不变      │ ────────────► │  轻量级转发    │                        │  run_agent()     │
  └──────────────────┘                 └──────────────┘                         └──────────────────┘

核心优势:
  - 进程可被 SIGKILL 瞬间强杀，不受 GIL 和网络阻塞影响
  - 沙盒隔离：Agent 崩溃不会影响主进程
  - 令行禁止：点停止 → SIGTERM(1s) → SIGKILL，灰飞烟灭

关键设计:
  - run_agent() 在 yield ask_user 后直接 return（生成器终止）
  - 因此子进程不需要双向 IPC，ask_user 后子进程自然结束
  - 父进程处理用户回答后，启动新子进程继续执行
"""

import os
import sys
import queue
import logging
import multiprocessing
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

MP_CTX = multiprocessing.get_context("spawn")

_active_processes: Dict[str, Dict[str, Any]] = {}


def _ensure_import_path(config: dict):
    sandbox_dir = os.path.dirname(os.path.abspath(__file__))
    if sandbox_dir not in sys.path:
        sys.path.insert(0, sandbox_dir)
    work_dir = config.get("work_dir", ".")
    if work_dir and work_dir not in sys.path:
        sys.path.insert(0, work_dir)


def _agent_entrypoint(event_queue: multiprocessing.Queue, config: dict):
    try:
        _ensure_import_path(config)

        # ── 跨进程上下文恢复：子进程第一件事就是注入 user_id ──
        user_id = config.get("user_id", 0)
        if user_id:
            from task_manager import ctx_user_id
            ctx_user_id.set(user_id)

        from agent_runner import run_agent, route_task, build_system_prompt, MAX_TURNS

        user_input = config["user_input"]
        work_dir = config.get("work_dir", ".")
        max_turns = config.get("max_turns", MAX_TURNS)
        api_key = config.get("api_key")
        model = config.get("model")
        base_url = config.get("base_url")
        provider = config.get("provider", "openai")
        initial_messages = config.get("initial_messages")
        start_turn = config.get("start_turn", 1)
        task_id = config.get("task_id")
        main_repo_dir = config.get("main_repo_dir")
        auto_approve = config.get("auto_approve", False)
        use_swarm = config.get("use_swarm", False)
        enable_routing = config.get("enable_routing", False)
        images = config.get("images") or []
        skills = config.get("skills") or []

        is_new_task = not initial_messages

        expert_label = ""
        persona_prompt = ""
        effective_input = user_input
        effective_images = images

        if is_new_task and user_input:
            if effective_images:
                from agent_prompts import VISION_ARCHITECT_EXPERT

                expert_label = "vision_architect (视觉架构师)"

                base_prompt = build_system_prompt(work_dir)
                persona_prompt = (
                    f"{base_prompt}\n\n# 🎯 专家身份激活\n"
                    f"你当前以 **视觉架构师** 专家身份执行任务。"
                    f"以下是你的专家指导原则：\n\n{VISION_ARCHITECT_EXPERT}"
                )
                logger.info(
                    f"[Subprocess] 检测到图片输入，直接指定视觉架构师 | 图片数: {len(effective_images)}"
                )
            else:
                event_queue.put({"type": "status", "data": "正在分析任务，选择专家..."})

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
                    f"[Subprocess] 路由完成: {expert_label}, 执行环境: {cto_execution_env}"
                )

                event_queue.put({
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
                    persona_prompt = (
                        f"{base_prompt}\n\n# 🎯 专家身份激活\n"
                        f"你当前以 **{expert_label}** 专家身份执行任务。"
                        f"以下是你的专家指导原则：\n\n{dynamic_prompt}"
                    )
                elif not is_predefined and target_agent == "general_coder":
                    persona_prompt = ""
                else:
                    from agent_prompts import get_expert_prompt
                    ep = get_expert_prompt(target_agent)
                    if ep:
                        persona_prompt = (
                            f"{base_prompt}\n\n# 🎯 专家身份激活\n"
                            f"你当前以 **{target_agent}** 专家身份执行任务。"
                            f"以下是你的专家指导原则：\n\n{ep}"
                        )
                    else:
                        persona_prompt = ""

        if skills and is_new_task:
            from prompt_builder import get_prompt_builder
            builder = get_prompt_builder()
            skill_prompt = builder.build_skill_prompt(skills)
            if skill_prompt:
                if persona_prompt:
                    persona_prompt = (
                        f"{persona_prompt}\n\n{'=' * 60}\n"
                        f"# 🎯 附加技能激活\n{'=' * 60}\n\n{skill_prompt}"
                    )
                else:
                    base_prompt = build_system_prompt(work_dir)
                    persona_prompt = (
                        f"{base_prompt}\n\n{'=' * 60}\n"
                        f"# 🎯 技能激活\n{'=' * 60}\n\n{skill_prompt}"
                    )
                logger.info(f"[Subprocess] 技能提示词已注入: {skills}")

        plan_mode = bool(skills and "plan" in skills)
        if plan_mode:
            logger.info("[Subprocess] PM需求澄清模式已激活")

        sdd_mode = bool(skills and "sdd" in skills)

        if sdd_mode and is_new_task:
            logger.info(f"[Subprocess] SDD 多智能体协作模式")

            event_queue.put({
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
                user_id=user_id,
            ):
                event_queue.put(event)

        elif use_swarm and is_new_task and persona_prompt:
            logger.info(f"[Subprocess] 深度模式 → 红蓝对抗 | 专家: {expert_label}")

            event_queue.put({
                "type": "debate_loop_start",
                "data": {
                    "expert_label": expert_label,
                    "sub_task": effective_input,
                    "dynamic_persona": bool(persona_prompt),
                },
            })

            event_queue.put({
                "type": "system_alert",
                "content": (
                    f"⚔️ 红蓝对抗引擎启动！蓝军继承 [{expert_label}] 专家身份，"
                    f"红军从该领域最佳实践角度深度挑刺"
                ),
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
                user_id=user_id,
            ):
                event_queue.put(event)

            event_queue.put({
                "type": "debate_loop_end",
                "data": {"expert_label": expert_label},
            })

        elif use_swarm:
            logger.info("[Subprocess] 深度模式 → 直接红蓝对抗 (继续任务)")
            from agent_swarm import run_swarm
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
                user_id=user_id,
            ):
                event_queue.put(event)

        else:
            mode_tag = f"穿 [{expert_label}] 专家外衣" if persona_prompt else "默认全栈"
            logger.info(f"[Subprocess] 极速模式 → 单体 Agent {mode_tag}")

            if persona_prompt:
                event_queue.put({
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
                event_queue.put(event)

    except Exception as e:
        logger.error(f"[Subprocess] Agent 异常: {e}", exc_info=True)
        event_queue.put({"type": "error", "data": f"Agent 子进程异常: {str(e)}"})
    finally:
        event_queue.put(None)


def start_agent_process(
    session_id: str, config: dict
) -> Tuple[multiprocessing.Process, multiprocessing.Queue]:
    event_queue = MP_CTX.Queue()

    process = MP_CTX.Process(
        target=_agent_entrypoint,
        args=(event_queue, config),
        name=f"agent-{session_id[:8] if session_id else 'unknown'}",
        daemon=True,
    )
    process.start()

    _active_processes[session_id] = {
        "process": process,
        "event_queue": event_queue,
        "created_at": __import__("time").time(),
    }

    logger.info(f"🚀 Agent 子进程已启动: session={session_id}, pid={process.pid}")
    return process, event_queue


def kill_agent_process(session_id: str, timeout: float = 1.0) -> bool:
    info = _active_processes.pop(session_id, None)
    if not info:
        return False

    process = info["process"]
    event_queue = info["event_queue"]

    if not process.is_alive():
        _cleanup_queue(event_queue)
        return True

    pid = process.pid
    logger.info(f"🛑 SIGTERM → Agent 子进程: session={session_id}, pid={pid}")
    process.terminate()
    process.join(timeout)

    if process.is_alive():
        logger.warning(
            f"💀 SIGTERM 无效，SIGKILL → Agent 子进程: session={session_id}, pid={pid}"
        )
        process.kill()
        process.join(1)

    _cleanup_queue(event_queue)
    logger.info(f"✅ Agent 子进程已强杀: session={session_id}, pid={pid}")
    return True


def get_active_process(session_id: str) -> Optional[multiprocessing.Process]:
    info = _active_processes.get(session_id)
    return info["process"] if info else None


def is_process_alive(session_id: str) -> bool:
    info = _active_processes.get(session_id)
    return info["process"].is_alive() if info else False


def _cleanup_queue(q: multiprocessing.Queue):
    try:
        q.close()
        q.join_thread()
    except Exception:
        pass
