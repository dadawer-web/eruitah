"""
Eruitah 智能编程沙盒 - SessionManager (会话管理器)

核心设计:
  用户一句话 = 开启一个平行宇宙（独立任务）
  AI 提炼标题 = 给这个平行宇宙贴个标签
  记忆隔离 = 任务 A 的对话和代码，绝对不能串台到任务 B
  回退隔离 = 撤销任务 A，只会把任务 A 相关的代码回滚，任务 B 毫发无损
  多租户隔离 = 每个用户的任务元数据、快照、检查点物理隔离

架构:
  SessionManager = TaskRegistry (物理快照) + TaskManager (会话记忆) 的统一入口
  - register_task(): 新任务注册 + 强制物理快照
  - get_or_create_session(): 获取/创建任务会话
  - rollback_session(): 物理级回滚 (文件还原 + 记忆截断)
  - switch_session(): 切换任务 (保存当前 + 加载目标)
"""

import os
import json
import time
import uuid
import shutil
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

COMPACT_THRESHOLD = 999
COMPACT_KEEP_RECENT = 4

IGNORE_PATTERNS = {
    "node_modules", "__pycache__", ".git", "venv", ".venv",
    "dist", "build", ".next", ".nuxt", "target", ".gradle",
    ".eruitah_snapshots", ".checkpoints", ".eruitah_cache", ".tasks",
    ".user_data",
}


@dataclass
class TaskSession:
    id: str
    summary: str
    work_dir: str
    snapshot_path: str
    messages_before: List[Dict[str, Any]]
    messages: List[Dict[str, Any]]
    created_at: float
    updated_at: float = 0.0
    status: str = "active"
    current_turn: int = 0
    base_checkpoint_id: str = ""
    worktree_dir: str = ""
    base_task_id: str = ""
    merge_commit_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.id,
            "summary": self.summary,
            "work_dir": self.work_dir,
            "snapshot_path": self.snapshot_path,
            "messages_before": self.messages_before,
            "messages": self.messages,
            "created_at": self.created_at,
            "updated_at": self.updated_at or self.created_at,
            "status": self.status,
            "current_turn": self.current_turn,
            "base_checkpoint_id": self.base_checkpoint_id,
            "worktree_dir": self.worktree_dir,
            "base_task_id": self.base_task_id,
            "merge_commit_hash": self.merge_commit_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskSession":
        return cls(
            id=data.get("task_id", data.get("id", "")) or "",
            summary=data.get("summary", "") or "",
            work_dir=data.get("work_dir", "") or "",
            snapshot_path=data.get("snapshot_path", "") or "",
            messages_before=data.get("messages_before") or [],
            messages=data.get("messages") or [],
            created_at=data.get("created_at") or time.time(),
            updated_at=data.get("updated_at") or 0.0,
            status=data.get("status", "active") or "active",
            current_turn=data.get("current_turn", 0) or 0,
            base_checkpoint_id=data.get("base_checkpoint_id", "") or "",
            worktree_dir=data.get("worktree_dir", "") or "",
            base_task_id=data.get("base_task_id", "") or "",
            merge_commit_hash=data.get("merge_commit_hash", "") or "",
        )


class SessionManager:
    def __init__(self, user_id: int):
        if not user_id:
            logger.warning("SessionManager created with user_id=0, falling back to 1 for tenant isolation")
            user_id = 1
        self._user_id = user_id
        self._sessions: Dict[str, TaskSession] = {}
        self.current_task_id: Optional[str] = None
        self._lock = threading.Lock()
        self._sandboxes: Dict[str, Any] = {}
        self._load_all()

    def _get_sandbox(self, work_dir: str):
        from sandbox_manager import get_sandbox
        return get_sandbox(work_dir)

    def _task_filepath(self, task_id: str) -> str:
        from sandbox_isolation import get_user_task_filepath
        return get_user_task_filepath(self._user_id, task_id)

    def _snapshot_path(self, task_id: str) -> str:
        from sandbox_isolation import get_user_snapshot_path
        return get_user_snapshot_path(self._user_id, task_id)

    def _task_dir(self) -> str:
        from sandbox_isolation import get_user_task_dir
        return get_user_task_dir(self._user_id)

    def _ignore_filter(self, directory: str, contents: list) -> list:
        return [name for name in contents if name in IGNORE_PATTERNS]

    def _load_all(self):
        from sandbox_isolation import get_user_task_dir
        task_dir = get_user_task_dir(self._user_id)
        if os.path.exists(task_dir):
            for filename in os.listdir(task_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(task_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        session = TaskSession.from_dict(data)
                        self._sessions[session.id] = session
                    except Exception as e:
                        logger.error(f"加载任务失败 {filename}: {e}")
        logger.info(f"SessionManager(user={self._user_id}) 已加载 {len(self._sessions)} 个任务会话")

    def _save_session(self, session: TaskSession):
        filepath = self._task_filepath(session.id)
        try:
            # 防空覆盖兜底：如果当前消息为空，但磁盘上已有历史记录，禁止覆盖
            if not session.messages:
                if os.path.exists(filepath):
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            disk_data = json.load(f)
                        disk_messages = disk_data.get("messages") or []
                        if disk_messages:
                            logger.warning(
                                f"⚠️ 跳过保存：当前会话消息为 0，防止覆盖已有历史记录 "
                                f"(task={session.id}, 磁盘已有 {len(disk_messages)} 条消息)"
                            )
                            # 用磁盘数据恢复内存中的 messages，防止后续操作继续用空列表
                            session.messages = disk_messages
                            return
                    except Exception as e:
                        logger.warning(f"读取磁盘历史记录失败，允许保存空会话: {e}")
            # 每次保存时刷新 updated_at
            session.updated_at = time.time()
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存任务失败 {session.id}: {e}")

    def _restore_messages_from_disk(self, session: TaskSession):
        """从磁盘恢复 session 的 messages，防止内存中空列表覆盖磁盘历史记录"""
        if session.messages:
            return  # 内存中已有消息，无需恢复
        filepath = self._task_filepath(session.id)
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                disk_data = json.load(f)
            disk_messages = disk_data.get("messages") or []
            if disk_messages:
                session.messages = disk_messages
                logger.info(f"🔄 从磁盘恢复了 {len(disk_messages)} 条消息到 session {session.id}")
        except Exception as e:
            logger.warning(f"从磁盘恢复消息失败 {session.id}: {e}")

    def _create_physical_snapshot(self, task_id: str, work_dir: str) -> str:
        snapshot_path = self._snapshot_path(task_id)
        if os.path.exists(work_dir):
            os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
            if os.path.exists(snapshot_path):
                shutil.rmtree(snapshot_path, ignore_errors=True)
            shutil.copytree(
                work_dir,
                snapshot_path,
                ignore=self._ignore_filter,
                dirs_exist_ok=True,
            )
            logger.info(f"📦 物理快照已创建: {work_dir} → {snapshot_path}")
        else:
            logger.warning(f"工作目录不存在，跳过快照: {work_dir}")
        return snapshot_path

    def get_or_create_session(
        self,
        task_id: Optional[str],
        first_prompt: str,
        work_dir: str,
        existing_messages: Optional[List[Dict[str, Any]]] = None,
        base_task_id: str = "",
        use_worktree: bool = True,
        is_independent_task: bool = False,
    ) -> TaskSession:
        with self._lock:
            if task_id and task_id in self._sessions:
                session = self._sessions[task_id]
                logger.info(f"🔄 继续任务 {task_id}: {len(session.messages)} 条历史消息")
                return session

            new_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
            summary = first_prompt[:50] + ("..." if len(first_prompt) > 50 else "")

            logger.info(f"📦 检测到新任务请求: {new_id}")

            worktree_dir = ""
            if use_worktree:
                sandbox = self._get_sandbox(work_dir)
                worktree_dir = sandbox.create_task_workspace(
                    new_id,
                    base_task_id=base_task_id,
                    user_id=self._user_id,
                    session_id=new_id,
                    is_independent_task=is_independent_task,
                )
            else:
                worktree_dir = work_dir
                logger.info(f"📦 直通模式: 任务 {new_id} 直接在用户目录 {work_dir} 工作")

            messages_before = existing_messages.copy() if existing_messages else []

            session = TaskSession(
                id=new_id,
                summary=summary,
                work_dir=work_dir,
                snapshot_path="",
                messages_before=messages_before,
                messages=[],
                created_at=time.time(),
                updated_at=time.time(),
                status="active",
                current_turn=0,
                base_checkpoint_id=f"task/{new_id}",
                worktree_dir=worktree_dir,
                base_task_id=base_task_id,
            )

            self._sessions[new_id] = session
            self._save_session(session)
            self.current_task_id = new_id

            if use_worktree:
                logger.info(f"📦 任务 {new_id} 已注册 (Git 分支: task/{new_id}): {summary}")
            else:
                logger.info(f"📦 任务 {new_id} 已注册 (直通模式): {summary}")
            return session

    def _is_passthrough(self, session: TaskSession) -> bool:
        return session.worktree_dir == session.work_dir

    def rollback_session(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._sessions:
                return {"success": False, "error": f"任务 {task_id} 不存在"}

            session = self._sessions[task_id]

            if session.status == "rolled_back":
                return {"success": False, "error": f"任务 {task_id} 已被回退过"}

            work_dir = session.work_dir
            logger.info(f"⏪ 物理回退任务 {task_id}: {session.summary[:50]}")

            try:
                from rewind_system import get_rewind_system
                rewind = get_rewind_system(user_id=self._user_id, session_id=task_id)

                rewind_result = rewind.rewind(
                    session_id=task_id,
                    to_turn=0,
                    work_dir=session.worktree_dir or work_dir,
                )

                if not rewind_result.get("success"):
                    sandbox = self._get_sandbox(work_dir)
                    result = sandbox.rollback_to_task_start(task_id)
                    if not result.get("success"):
                        return result
                else:
                    result = rewind_result

                session.status = "rolled_back"
                session.messages = []
                session.current_turn = 0
                self._save_session(session)

                logger.info(f"⏪ 物理回退完成: {task_id}")

                return {
                    "success": True,
                    "task_id": task_id,
                    "summary": session.summary,
                    "messages_before": session.messages_before,
                    "work_dir": work_dir,
                    "reverted_files": result.get("reverted_files", []),
                    "changed_files_raw": result.get("changed_files_raw", ""),
                    "stat_summary": result.get("stat_summary", ""),
                    "detailed_diff": result.get("detailed_diff", ""),
                    "commits_being_reverted": result.get("commits_being_reverted", ""),
                    "untracked_files": result.get("untracked_files", ""),
                }

            except Exception as e:
                logger.error(f"⏪ 物理回退失败: {e}")
                return {"success": False, "error": str(e)}

    def switch_session(
        self,
        new_task_id: str,
        current_messages: Optional[List[Dict[str, Any]]] = None,
        current_turn: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if self.current_task_id and self.current_task_id in self._sessions:
                old_session = self._sessions[self.current_task_id]
                if current_messages is not None:
                    old_session.messages = current_messages
                else:
                    # 没有传入 current_messages 时，从磁盘恢复，防止空列表覆盖
                    self._restore_messages_from_disk(old_session)
                old_session.messages = old_session.messages or []
                if current_turn is not None:
                    old_session.current_turn = current_turn
                self._save_session(old_session)
                logger.info(f"💾 已保存当前任务 {self.current_task_id}: {len(old_session.messages)} 条消息")

            if new_task_id not in self._sessions:
                return {"success": False, "error": f"任务 {new_task_id} 不存在"}

            self.current_task_id = new_task_id
            target = self._sessions[new_task_id]

            if target.status in ("merged", "reverted"):
                effective_work_dir = target.work_dir
                logger.info(f"🔄 切换到已{'合并' if target.status == 'merged' else 'revert'}任务 {new_task_id}，重定向到主干: {effective_work_dir}")
            else:
                sandbox = self._get_sandbox(target.work_dir)
                worktree_dir = sandbox.switch_to_task(new_task_id)
                if worktree_dir and not target.worktree_dir:
                    target.worktree_dir = worktree_dir
                    self._save_session(target)
                effective_work_dir = target.worktree_dir or target.work_dir
                logger.info(f"🔄 切换到任务 {new_task_id}: {target.summary[:50]}")

            return {
                "success": True,
                "task_id": new_task_id,
                "summary": target.summary,
                "messages": target.messages,
                "messages_before": target.messages_before,
                "current_turn": target.current_turn,
                "work_dir": effective_work_dir,
            }

    def update_session_messages(
        self,
        task_id: str,
        messages: List[Dict[str, Any]],
        current_turn: int = 0,
    ):
        with self._lock:
            if task_id in self._sessions:
                session = self._sessions[task_id]
                effective_messages = messages or []
                # 防空覆盖：传入空消息时不覆盖磁盘上已有的历史记录
                if not effective_messages and session.messages:
                    logger.warning(
                        f"⚠️ update_session_messages: 传入空消息但 session 已有 {len(session.messages)} 条，跳过覆盖"
                    )
                else:
                    session.messages = effective_messages
                session.current_turn = current_turn
                self._save_session(session)

                if len(session.messages) > COMPACT_THRESHOLD:
                    self._compact_session_memory(task_id)

    def _compact_session_memory(self, session_id: str):
        if session_id not in self._sessions:
            return

        session = self._sessions[session_id]
        messages = session.messages or []

        if len(messages) <= COMPACT_THRESHOLD:
            return

        system_msg = None
        start_idx = 0
        if messages and messages[0].get("role") == "system":
            system_msg = messages[0]
            start_idx = 1

        middle_end = len(messages) - COMPACT_KEEP_RECENT
        if middle_end <= start_idx:
            return

        middle_messages = messages[start_idx:middle_end]
        recent_messages = messages[middle_end:]

        summary = self._call_cheap_llm_for_summary(middle_messages)

        compacted = []
        if system_msg:
            compacted.append(system_msg)

        compacted.append({
            "role": "system",
            "content": f"📚 历史压缩摘要 (自动生成，原始 {len(middle_messages)} 条消息已压缩):\n{summary}",
        })

        compacted.extend(recent_messages)

        session.messages = compacted
        self._save_session(session)

        logger.info(
            f"📦 任务 {session_id} 上下文已压缩: "
            f"{len(messages)} → {len(compacted)} 条消息 "
            f"(压缩了 {len(middle_messages)} 条中间对话)"
        )

    def compact_memory(self, session_id: str):
        with self._lock:
            self._compact_session_memory(session_id)

    def _call_cheap_llm_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        structured_summary = self._generate_summary(messages)

        try:
            import os
            summary_api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            summary_base_url = os.environ.get("OPENAI_BASE_URL")
            if summary_base_url and not summary_base_url.endswith("/v1"):
                summary_base_url = summary_base_url.rstrip("/") + "/v1"
            summary_model = os.environ.get("ERUITAH_SUMMARY_MODEL", "mimo-v2.5-pro")

            if not summary_api_key:
                return structured_summary

            from openai import OpenAI
            client = OpenAI(api_key=summary_api_key, base_url=summary_base_url)

            conversation_text = self._messages_to_text(messages)

            response = client.chat.completions.create(
                model=summary_model,
                messages=[
                    {"role": "system", "content": "你是一个代码助手的历史对话压缩器。请将以下对话历史压缩为一段简洁的摘要，保留：1) 用户的核心意图 2) 已执行的关键操作 3) 遇到的错误和解决方案。忽略冗余的试错过程。用中文输出，不超过200字。"},
                    {"role": "user", "content": f"请压缩以下对话历史：\n\n{conversation_text[:3000]}"},
                ],
                max_tokens=300,
                temperature=0.3,
            )

            llm_summary = response.choices[0].message.content.strip()
            if llm_summary:
                logger.info(f"🧠 LLM 压缩摘要生成成功: {llm_summary[:80]}...")
                return llm_summary
        except Exception as e:
            logger.debug(f"LLM 摘要生成失败，回退到结构化摘要: {e}")

        return structured_summary

    def _messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = str(msg.get("content", ""))[:200]
            if role == "user":
                lines.append(f"[用户] {content}")
            elif role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            fn = tc.get("function", tc)
                            if isinstance(fn, dict):
                                name = fn.get("name", "?")
                                lines.append(f"[助手→工具] {name}")
                elif content:
                    lines.append(f"[助手] {content[:100]}")
            elif role == "tool":
                if "error" in content.lower() or "失败" in content:
                    lines.append(f"[工具结果-错误] {content[:80]}")
                else:
                    lines.append(f"[工具结果] {content[:50]}")
            elif role == "system":
                lines.append(f"[系统] {content[:100]}")
        return "\n".join(lines)

    def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        user_intents = []
        tool_actions = []
        errors = []

        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content", ""))

            if role == "user" and content:
                user_intents.append(content[:100])
            elif role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            fn = tc.get("function", tc)
                            if isinstance(fn, dict):
                                name = fn.get("name", "")
                                args_str = fn.get("arguments", "{}")
                                try:
                                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                                except Exception:
                                    args = {}
                                if name == "file_edit":
                                    fp = args.get("file_path", "?")
                                    tool_actions.append(f"编辑文件: {fp}")
                                elif name == "bash":
                                    cmd = args.get("command", "?")
                                    tool_actions.append(f"执行命令: {cmd[:60]}")
                                elif name == "file_read":
                                    fp = args.get("file_path", "?")
                                    tool_actions.append(f"读取文件: {fp}")
                                else:
                                    tool_actions.append(f"调用工具: {name}")
            elif role == "tool":
                if "error" in content.lower() or "失败" in content:
                    errors.append(content[:80])

        parts = []

        if user_intents:
            unique_intents = list(dict.fromkeys(user_intents))[:5]
            parts.append("用户意图: " + " → ".join(unique_intents))

        if tool_actions:
            unique_actions = list(dict.fromkeys(tool_actions))[:10]
            parts.append("执行操作: " + "; ".join(unique_actions))

        if errors:
            parts.append("遇到错误: " + "; ".join(errors[:3]))

        if not parts:
            return f"[系统折叠了前期的试错日志] ({len(messages)} 条消息)"

        return "\n".join(parts)

    def list_sessions(self, work_dir: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            sessions = []
            for session in self._sessions.values():
                if work_dir:
                    sdir = session.work_dir or ""
                    if sdir != work_dir and not sdir.startswith(work_dir) and not work_dir.startswith(sdir):
                        continue

                # 旧数据兼容：如果 created_at 缺失或为 0，用磁盘文件 mtime 回填
                if not session.created_at:
                    filepath = self._task_filepath(session.id)
                    if os.path.exists(filepath):
                        mtime = os.path.getmtime(filepath)
                        session.created_at = mtime
                    else:
                        session.created_at = time.time()

                # 旧数据兼容：如果 updated_at 缺失或为 0，用 created_at 回填
                if not session.updated_at:
                    session.updated_at = session.created_at

                d = session.to_dict()
                # 注入 ISO 8601 格式的时间字符串，前端直接可用
                from datetime import datetime
                d["created_at_iso"] = datetime.fromtimestamp(session.created_at).isoformat()
                d["updated_at_iso"] = datetime.fromtimestamp(session.updated_at).isoformat()
                d["created_at_str"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session.created_at))
                d["updated_at_str"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session.updated_at))
                sessions.append(d)
            sessions.sort(key=lambda t: t.get("created_at", 0), reverse=True)
            return sessions

    def get_session(self, task_id: str) -> Optional[TaskSession]:
        with self._lock:
            return self._sessions.get(task_id)

    def set_session_status(self, task_id: str, status: str):
        with self._lock:
            if task_id in self._sessions:
                self._sessions[task_id].status = status
                self._save_session(self._sessions[task_id])

    def delete_session(self, task_id: str):
        with self._lock:
            if task_id in self._sessions:
                session = self._sessions[task_id]
                if os.path.exists(session.snapshot_path):
                    shutil.rmtree(session.snapshot_path, ignore_errors=True)
                filepath = self._task_filepath(task_id)
                if os.path.exists(filepath):
                    os.unlink(filepath)
                del self._sessions[task_id]
                logger.info(f"已删除任务: {task_id}")

    def merge_session(self, task_id: str, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._sessions:
                return {"status": "error", "message": f"任务 {task_id} 不存在"}

            session = self._sessions[task_id]

            if session.status == "merged":
                return {"status": "error", "message": f"任务 {task_id} 已经合并过了"}

            if self._is_passthrough(session):
                session.status = "merged"
                self._save_session(session)
                return {"status": "success", "message": "直通模式下文件已在原目录，无需合并", "task_id": task_id}

            sandbox = self._get_sandbox(session.work_dir)
            result = sandbox.merge_task_to_main(task_id, force=force)

            if result.get("status") == "success":
                session.status = "merged"
                session.merge_commit_hash = result.get("merge_commit_hash", "")
                self._save_session(session)
                logger.info(f"✅ 任务 {task_id} 已合并到主干 (merge_commit={session.merge_commit_hash})")
            elif result.get("status") == "conflict":
                session.status = "conflict"
                self._save_session(session)
                logger.warning(f"⚠️ 任务 {task_id} 合并冲突，等待人工解决")

            return result

    def rollback_step_session(self, task_id: str, steps: int = 1) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._sessions:
                return {"success": False, "error": f"任务 {task_id} 不存在"}

            session = self._sessions[task_id]

            if session.status not in ("active",):
                return {"success": False, "error": f"任务 {task_id} 状态为 {session.status}，无法回退步骤"}

            work_dir = session.worktree_dir or session.work_dir

            try:
                from rewind_system import get_rewind_system
                rewind = get_rewind_system(user_id=self._user_id, session_id=task_id)

                rewind_result = rewind.rewind(
                    session_id=task_id,
                    steps=steps,
                    work_dir=work_dir,
                )

                if rewind_result.get("success"):
                    restored_messages = rewind_result.get("messages", [])
                    session.messages = restored_messages
                    session.current_turn = rewind_result.get("target_turn", 0)
                    self._save_session(session)

                    logger.info(f"⏪ 任务 {task_id} 回退 {steps} 步 (Hybrid Pointer), target_turn={session.current_turn}")

                    return {
                        "success": True,
                        "steps_rolled_back": steps,
                        "target_turn": session.current_turn,
                        "reverted_files": rewind_result.get("reverted_files", []),
                        "changed_files_raw": rewind_result.get("changed_files_raw", ""),
                        "stat_summary": rewind_result.get("stat_summary", ""),
                        "detailed_diff": rewind_result.get("detailed_diff", ""),
                        "commits_being_reverted": rewind_result.get("commits_being_reverted", ""),
                    }
            except Exception as e:
                logger.warning(f"rewind_system 步骤回退失败，降级到 sandbox_manager: {e}")

            sandbox = self._get_sandbox(session.work_dir)
            result = sandbox.rollback_task_step(task_id, steps=steps)

            if result.get("success"):
                msg_count = len(session.messages)
                trim_count = min(steps * 2, msg_count)
                if trim_count > 0 and msg_count > trim_count:
                    session.messages = session.messages[:-trim_count]
                session.current_turn = max(0, session.current_turn - steps)
                self._save_session(session)
                logger.info(f"⏪ 任务 {task_id} 回退 {result.get('steps_rolled_back', steps)} 步，消息裁剪 {trim_count} 条")

            return result

    def revert_merged_session(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._sessions:
                return {"status": "error", "message": f"任务 {task_id} 不存在"}

            session = self._sessions[task_id]

            if session.status != "merged":
                return {"status": "error", "message": f"任务 {task_id} 状态为 {session.status}，只能 revert 已合并的任务"}

            if self._is_passthrough(session):
                session.status = "reverted"
                self._save_session(session)
                return {"status": "success", "message": "直通模式下无需 revert，文件已在原目录", "task_id": task_id}

            if not session.merge_commit_hash:
                return {"status": "error", "message": f"任务 {task_id} 没有记录 merge commit hash，无法 revert"}

            sandbox = self._get_sandbox(session.work_dir)
            result = sandbox.revert_merged_task(task_id, session.merge_commit_hash)

            if result.get("status") == "success":
                session.status = "reverted"
                self._save_session(session)
                logger.info(f"🚑 任务 {task_id} 已通过 revert 安全抵消")

            return result


_session_managers: Dict[int, SessionManager] = {}
_managers_lock = threading.Lock()


def get_session_manager(user_id: int = 0) -> SessionManager:
    if not user_id:
        user_id = int(os.environ.get("ERUITAH_DEFAULT_USER_ID", "0"))
    if not user_id:
        user_id = 1
        logger.warning(
            "get_session_manager() called without user_id, falling back to 1. "
            "This breaks tenant isolation! Pass user_id explicitly or set ERUITAH_DEFAULT_USER_ID."
        )
    with _managers_lock:
        if user_id not in _session_managers:
            _session_managers[user_id] = SessionManager(user_id=user_id)
        return _session_managers[user_id]


def get_task_manager(user_id: int = 0) -> SessionManager:
    return get_session_manager(user_id=user_id)
