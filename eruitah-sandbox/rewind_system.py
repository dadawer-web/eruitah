"""
Eruitah 智能编程沙盒 - 会话回退系统 v2 (Hybrid Pointer Architecture)

核心思想（工业级指针级融合）:
┌─────────────────────────────────────────────────────────────────────┐
│  Git 存肉体，SQLite 存灵魂（指针映射）                               │
│                                                                     │
│  ❌ 旧方案: 每轮存全量文件快照 → O(N^2) 磁盘 I/O 爆炸              │
│  ✅ 新方案: 每轮只存 Git Commit Hash → O(1) 极致轻量               │
│                                                                     │
│  检查点数据结构:                                                    │
│    {                                                                │
│      "turn": 15,                                                    │
│      "messages": [...],               ← 灵魂：对话记忆             │
│      "git_commit": "a3f7c2d...",      ← 肉体：Git 指针（40字符）  │
│      "diff_stat": "2 files changed"   ← 前端展示用 diff 摘要       │
│    }                                                                │
│                                                                     │
│  时光倒流:                                                          │
│    1. 从 SQLite 查出目标轮次的 git_commit                           │
│    2. 恢复灵魂: 把过去的 messages 塞回给大模型                      │
│    3. 恢复肉体: git reset --hard <git_commit>                      │
│                                                                     │
│  优势:                                                              │
│    - 磁盘: 从 O(N^2) 降到 O(N)，不再存文件内容                     │
│    - 查询: Git Commit Hash 只有 40 字符                             │
│    - 并发: 多 Agent 同时存快照不会击穿 I/O                          │
│    - 增量: Git 内部已经是增量存储（delta compression）              │
└─────────────────────────────────────────────────────────────────────┘

参考: Cursor / Trae 底层 Hybrid Pointer Architecture
"""

import os
import json
import time
import sqlite3
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

CHECKPOINT_DB = os.environ.get(
    "ERUITAH_CHECKPOINT_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".checkpoints", "rewind.db"),
)


@dataclass
class Checkpoint:
    session_id: str
    turn: int
    timestamp: float
    messages: List[Dict[str, Any]]
    git_commit: str = ""
    diff_stat: str = ""
    description: str = ""
    code_diff: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "timestamp": self.timestamp,
            "messages": self.messages,
            "git_commit": self.git_commit,
            "diff_stat": self.diff_stat,
            "description": self.description,
            "code_diff": self.code_diff,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "Checkpoint":
        messages = []
        if row[4]:
            try:
                messages = json.loads(row[4])
            except (json.JSONDecodeError, TypeError):
                messages = []
        code_diff = ""
        if len(row) > 7 and row[7]:
            code_diff = row[7]
        return cls(
            session_id=row[0],
            turn=row[1],
            timestamp=row[2],
            description=row[3] or "",
            messages=messages,
            git_commit=row[5] or "",
            diff_stat=row[6] or "",
            code_diff=code_diff,
        )


class RewindSystem:
    def __init__(self):
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(CHECKPOINT_DB), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(CHECKPOINT_DB)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                session_id TEXT NOT NULL,
                turn INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                description TEXT DEFAULT '',
                messages_json TEXT DEFAULT '[]',
                git_commit TEXT DEFAULT '',
                diff_stat TEXT DEFAULT '',
                code_diff TEXT DEFAULT '',
                PRIMARY KEY (session_id, turn)
            );
            CREATE INDEX IF NOT EXISTS idx_session ON checkpoints(session_id);
        """)
        try:
            conn.execute("ALTER TABLE checkpoints ADD COLUMN code_diff TEXT DEFAULT ''")
        except Exception:
            pass
        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(CHECKPOINT_DB)

    def _sanitize_value(self, v) -> Any:
        if isinstance(v, (str, int, float, bool, type(None))):
            return v
        if isinstance(v, (list, tuple)):
            return [self._sanitize_value(item) for item in v]
        if isinstance(v, dict):
            return {k: self._sanitize_value(val) for k, val in v.items()}
        if hasattr(v, 'model_dump'):
            try:
                return v.model_dump()
            except Exception:
                pass
        if hasattr(v, '__dict__'):
            try:
                return {k: self._sanitize_value(val) for k, val in v.__dict__.items() if not k.startswith('_')}
            except Exception:
                pass
        try:
            json.dumps(v, ensure_ascii=False, default=str)
            return v
        except (TypeError, ValueError):
            return str(v)

    def _sanitize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sanitized = []
        for msg in messages:
            if not isinstance(msg, dict):
                if hasattr(msg, '__dict__'):
                    msg = vars(msg)
                else:
                    msg = {"role": "unknown", "content": str(msg)}
            clean = {}
            for k, v in msg.items():
                clean[k] = self._sanitize_value(v)
            if "content" in clean and isinstance(clean["content"], list):
                content_list = []
                for block in clean["content"]:
                    if isinstance(block, dict):
                        block_type = block.get("type", "")
                        if block_type == "text":
                            content_list.append({
                                "type": "text",
                                "text": str(block.get("text", "")),
                            })
                        elif block_type == "tool_use":
                            content_list.append({
                                "type": "tool_use",
                                "id": str(block.get("id", "")),
                                "name": str(block.get("name", "")),
                                "input": self._sanitize_value(block.get("input", {})),
                            })
                        elif block_type == "tool_result":
                            content_list.append({
                                "type": "tool_result",
                                "tool_use_id": str(block.get("tool_use_id", "")),
                                "content": self._sanitize_value(block.get("content", "")),
                                "is_error": block.get("is_error", False),
                            })
                        else:
                            content_list.append(self._sanitize_value(block))
                    elif isinstance(block, str):
                        content_list.append({"type": "text", "text": block})
                    else:
                        content_list.append(self._sanitize_value(block))
                clean["content"] = content_list
            sanitized.append(clean)
        return sanitized

    def _capture_git_diff(self, work_dir: str, turn: int = 0, description: str = "") -> tuple:
        git_commit = ""
        diff_stat = ""
        code_diff = ""

        if not work_dir or not os.path.exists(work_dir):
            return git_commit, diff_stat, code_diff

        git_dir = os.path.join(work_dir, ".git")
        if not os.path.exists(git_dir):
            return git_commit, diff_stat, code_diff

        try:
            import subprocess

            subprocess.run(
                ["git", "config", "user.name", "AI Agent"],
                capture_output=True, timeout=5, cwd=work_dir,
            )
            subprocess.run(
                ["git", "config", "user.email", "agent@eruitah.com"],
                capture_output=True, timeout=5, cwd=work_dir,
            )

            prev_commit = ""
            rev_before = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=work_dir,
            )
            if rev_before.returncode == 0:
                prev_commit = rev_before.stdout.strip()

            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=5, cwd=work_dir,
            )

            has_changes = bool(status_result.stdout.strip())

            if has_changes:
                subprocess.run(
                    ["git", "add", "-A"],
                    capture_output=True, timeout=5, cwd=work_dir,
                )
                commit_msg = f"checkpoint: turn {turn}"
                if description:
                    commit_msg += f" - {description[:60]}"
                commit_result = subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    capture_output=True, text=True, timeout=10, cwd=work_dir,
                )
                if commit_result.returncode != 0:
                    logger.warning(f"Git commit 失败: {commit_result.stderr.strip()[:200]}")

            rev_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=work_dir,
            )
            if rev_result.returncode == 0:
                git_commit = rev_result.stdout.strip()

            if not has_changes:
                return git_commit, "", ""

            if prev_commit and git_commit and git_commit != prev_commit:
                stat_result = subprocess.run(
                    ["git", "diff", "--stat", prev_commit, git_commit],
                    capture_output=True, text=True, timeout=10, cwd=work_dir,
                )
                diff_stat = stat_result.stdout.strip() if stat_result.returncode == 0 else ""

                diff_result = subprocess.run(
                    ["git", "diff", prev_commit, git_commit],
                    capture_output=True, text=True, timeout=15, cwd=work_dir,
                )
                code_diff = diff_result.stdout[:16000] if diff_result.returncode == 0 else ""

        except Exception as e:
            logger.debug(f"捕获 Git diff 失败: {e}")

        return git_commit, diff_stat, code_diff

    def create_checkpoint(
        self,
        session_id: str,
        turn: int,
        messages: List[Dict[str, Any]],
        description: str = "",
        git_commit: str = "",
        diff_stat: str = "",
        work_dir: str = "",
    ) -> Checkpoint:
        import copy
        frozen_messages = copy.deepcopy(messages)

        if work_dir and not git_commit:
            git_commit, diff_stat, code_diff = self._capture_git_diff(work_dir, turn=turn, description=description)
        else:
            code_diff = ""

        sanitized_messages = self._sanitize_messages(frozen_messages)

        checkpoint = Checkpoint(
            session_id=session_id,
            turn=turn,
            timestamp=time.time(),
            messages=sanitized_messages,
            git_commit=git_commit,
            diff_stat=diff_stat,
            description=description,
            code_diff=code_diff,
        )

        with self._lock:
            conn = self._get_conn()
            try:
                messages_json = json.dumps(
                    checkpoint.messages,
                    ensure_ascii=False,
                    default=str,
                )
                conn.execute(
                    """INSERT OR REPLACE INTO checkpoints
                       (session_id, turn, timestamp, description, messages_json, git_commit, diff_stat, code_diff)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        checkpoint.session_id,
                        checkpoint.turn,
                        checkpoint.timestamp,
                        checkpoint.description,
                        messages_json,
                        checkpoint.git_commit,
                        checkpoint.diff_stat,
                        checkpoint.code_diff,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        commit_info = f" commit={git_commit[:8]}" if git_commit else ""
        diff_info = f" diff={len(code_diff)}chars" if code_diff else ""
        logger.info(f"创建检查点 {session_id}:{turn}{commit_info}{diff_info} - {description}")
        return checkpoint

    def update_checkpoint_commit(
        self,
        session_id: str,
        turn: int,
        git_commit: str,
        diff_stat: str = "",
        description: str = "",
    ):
        with self._lock:
            conn = self._get_conn()
            try:
                if git_commit:
                    if description or diff_stat:
                        conn.execute(
                            """UPDATE checkpoints SET git_commit = ?, diff_stat = ?, description = ?
                               WHERE session_id = ? AND turn = ?""",
                            (git_commit, diff_stat, description or diff_stat, session_id, turn),
                        )
                    else:
                        conn.execute(
                            """UPDATE checkpoints SET git_commit = ?, diff_stat = ?
                               WHERE session_id = ? AND turn = ?""",
                            (git_commit, diff_stat, session_id, turn),
                        )
                else:
                    if description:
                        conn.execute(
                            """UPDATE checkpoints SET description = ?
                               WHERE session_id = ? AND turn = ? AND (description IS NULL OR description = '' OR description LIKE '第 %轮')""",
                            (description, session_id, turn),
                        )
                    if diff_stat:
                        conn.execute(
                            """UPDATE checkpoints SET diff_stat = ?
                               WHERE session_id = ? AND turn = ?""",
                            (diff_stat, session_id, turn),
                        )
                conn.commit()
            finally:
                conn.close()

        commit_info = f" commit={git_commit[:8]}" if git_commit else ""
        logger.info(f"检查点 {session_id}:{turn}{commit_info} desc={description[:40] if description else '-'}")

    def view_checkpoint(
        self,
        session_id: str,
        turn: int,
        work_dir: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT session_id, turn, timestamp, description, messages_json, git_commit, diff_stat, code_diff
                       FROM checkpoints WHERE session_id = ? AND turn = ?""",
                    (session_id, turn),
                ).fetchone()
            finally:
                conn.close()

        if not row:
            return {"success": False, "error": f"检查点 {session_id}:{turn} 不存在"}

        checkpoint = Checkpoint.from_row(row)

        result = {
            "success": True,
            "turn": checkpoint.turn,
            "timestamp": checkpoint.timestamp,
            "description": checkpoint.description,
            "git_commit": checkpoint.git_commit,
            "diff_stat": checkpoint.diff_stat,
            "messages": checkpoint.messages,
            "code_diff": checkpoint.code_diff,
            "diff_lines": [],
            "detailed_diff": "",
            "changed_files": [],
        }

        if checkpoint.code_diff:
            result["detailed_diff"] = checkpoint.code_diff
            result["diff_lines"] = self._parse_diff_to_lines(checkpoint.code_diff)

        if not checkpoint.code_diff and checkpoint.git_commit and work_dir and os.path.exists(work_dir):
            git_dir = os.path.join(work_dir, ".git")
            if os.path.exists(git_dir):
                try:
                    import subprocess

                    rev_check = subprocess.run(
                        ["git", "cat-file", "-t", checkpoint.git_commit],
                        capture_output=True, text=True, timeout=5, cwd=work_dir,
                    )
                    if rev_check.returncode != 0:
                        result["changed_files"] = self._parse_changed_files(checkpoint.diff_stat)
                        return result

                    parent_result = subprocess.run(
                        ["git", "rev-parse", f"{checkpoint.git_commit}~1"],
                        capture_output=True, text=True, timeout=5, cwd=work_dir,
                    )

                    if parent_result.returncode == 0:
                        parent_hash = parent_result.stdout.strip()
                        diff_result = subprocess.run(
                            ["git", "diff", parent_hash, checkpoint.git_commit],
                            capture_output=True, text=True, timeout=15, cwd=work_dir,
                        )
                    else:
                        diff_result = subprocess.run(
                            ["git", "show", checkpoint.git_commit, "--format=", "--stat", "-p"],
                            capture_output=True, text=True, timeout=15, cwd=work_dir,
                        )

                    raw_diff = diff_result.stdout
                    if raw_diff:
                        result["detailed_diff"] = raw_diff[:16000]
                        result["diff_lines"] = self._parse_diff_to_lines(raw_diff)

                    name_status_result = subprocess.run(
                        ["git", "diff", "--name-status", parent_hash if parent_result.returncode == 0 else "4b825dc642cb6eb9a060e54bf899d15363d7b90d", checkpoint.git_commit],
                        capture_output=True, text=True, timeout=5, cwd=work_dir,
                    )
                    result["changed_files"] = self._parse_changed_files(name_status_result.stdout.strip())

                    show_result = subprocess.run(
                        ["git", "show", checkpoint.git_commit, "--stat", "--format="],
                        capture_output=True, text=True, timeout=5, cwd=work_dir,
                    )
                    result["diff_stat"] = show_result.stdout.strip() or checkpoint.diff_stat

                except Exception as e:
                    logger.error(f"查看检查点 diff 异常: {e}")

        return result

    def rewind(
        self,
        session_id: str,
        steps: int = 1,
        to_turn: Optional[int] = None,
        work_dir: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT session_id, turn, timestamp, description, messages_json, git_commit, diff_stat, code_diff
                       FROM checkpoints WHERE session_id = ? ORDER BY turn ASC""",
                    (session_id,),
                ).fetchall()

                if not rows:
                    return {"success": False, "error": "没有可用的检查点"}

                checkpoints = [Checkpoint.from_row(r) for r in rows]

                if to_turn is not None:
                    target_idx = next(
                        (i for i, cp in enumerate(checkpoints) if cp.turn == to_turn),
                        -1,
                    )
                    if target_idx == -1:
                        return {
                            "success": False,
                            "error": f"找不到第 {to_turn} 轮的检查点",
                        }
                else:
                    target_idx = max(0, len(checkpoints) - steps)

                target_checkpoint = checkpoints[target_idx]
                removed_checkpoints = checkpoints[target_idx + 1:]

                git_result = self._restore_git_state(
                    target_checkpoint, removed_checkpoints, work_dir
                )

                removed_turns = [cp.turn for cp in removed_checkpoints]
                if removed_turns:
                    placeholders = ",".join("?" * len(removed_turns))
                    conn.execute(
                        f"""DELETE FROM checkpoints
                            WHERE session_id = ? AND turn IN ({placeholders})""",
                        [session_id] + removed_turns,
                    )
                    conn.commit()

            finally:
                conn.close()

        diff_info = self._build_diff_info(target_checkpoint, removed_checkpoints, git_result)

        logger.info(
            f"回退到检查点 {session_id}:{target_checkpoint.turn}，"
            f"git_reset={'成功' if git_result.get('success') else '跳过'}"
        )

        return {
            "success": True,
            "target_turn": target_checkpoint.turn,
            "target_timestamp": target_checkpoint.timestamp,
            "messages": target_checkpoint.messages,
            "git_commit": target_checkpoint.git_commit,
            **diff_info,
        }

    def _restore_git_state(
        self,
        target: Checkpoint,
        removed: List[Checkpoint],
        work_dir: str,
    ) -> Dict[str, Any]:
        if not work_dir or not os.path.exists(work_dir):
            logger.warning(f"工作目录不存在，跳过 Git 恢复: {work_dir}")
            return {"success": False, "reason": "work_dir_missing"}

        git_dir = os.path.join(work_dir, ".git")
        if not os.path.exists(git_dir):
            logger.info("工作目录不是 Git 仓库，跳过 Git 恢复")
            return {"success": False, "reason": "not_git_repo"}

        try:
            import subprocess

            target_commit = target.git_commit
            fallback_steps = len(removed) if removed else 1

            if not target_commit:
                logger.info(f"目标检查点无 Git Commit Hash，尝试 HEAD~{fallback_steps} 回退")
                rev_result = subprocess.run(
                    ["git", "rev-parse", f"HEAD~{fallback_steps}"],
                    capture_output=True, text=True, timeout=5, cwd=work_dir,
                )
                if rev_result.returncode != 0:
                    logger.info(f"HEAD~{fallback_steps} 不存在，尝试 HEAD~1")
                    rev_result = subprocess.run(
                        ["git", "rev-parse", "HEAD~1"],
                        capture_output=True, text=True, timeout=5, cwd=work_dir,
                    )
                if rev_result.returncode == 0:
                    target_commit = rev_result.stdout.strip()
                else:
                    logger.info("无法确定回退目标 commit，跳过 Git 恢复")
                    return {"success": False, "reason": "no_commit_hash"}

            head_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=work_dir,
            )
            if head_result.returncode == 0 and head_result.stdout.strip() == target_commit:
                logger.info("目标 commit 等于当前 HEAD，无需 Git 回退")
                return {"success": True, "reverted_files": [], "changed_files_raw": "",
                        "stat_summary": "", "detailed_diff": "", "commits_being_reverted": ""}

            diff_stat_result = subprocess.run(
                ["git", "diff", "--stat", target_commit, "HEAD"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            diff_stat = diff_stat_result.stdout.strip()

            diff_name_status = subprocess.run(
                ["git", "diff", "--name-status", target_commit, "HEAD"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            changed_files_raw = diff_name_status.stdout.strip()

            detailed_diff_result = subprocess.run(
                ["git", "diff", target_commit, "HEAD"],
                capture_output=True, text=True, timeout=30, cwd=work_dir,
            )
            detailed_diff = detailed_diff_result.stdout[:8000]

            log_result = subprocess.run(
                ["git", "log", "--oneline", f"{target_commit}..HEAD"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            commits_being_reverted = log_result.stdout.strip()

            reset_result = subprocess.run(
                ["git", "reset", "--hard", target_commit],
                capture_output=True, text=True, timeout=30, cwd=work_dir,
            )

            if reset_result.returncode != 0:
                logger.error(f"Git reset 失败: {reset_result.stderr.strip()[:300]}")
                return {"success": False, "reason": f"reset_failed: {reset_result.stderr.strip()[:200]}"}

            clean_result = subprocess.run(
                ["git", "clean", "-fd"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )

            file_list = self._parse_changed_files(changed_files_raw)

            logger.info(
                f"Git 时光倒流完成: reset --hard {target_commit[:8]} + clean -fd\n"
                f"  撤销 {len(file_list)} 个文件变更, {len(commits_being_reverted.split(chr(10)))} 个提交"
            )

            return {
                "success": True,
                "reverted_files": file_list,
                "changed_files_raw": changed_files_raw,
                "stat_summary": diff_stat,
                "detailed_diff": detailed_diff,
                "commits_being_reverted": commits_being_reverted,
            }

        except Exception as e:
            logger.error(f"Git 恢复异常: {e}")
            return {"success": False, "reason": str(e)}

    def _parse_changed_files(self, name_status_raw: str) -> List[Dict[str, Any]]:
        file_list = []
        if not name_status_raw:
            return file_list
        for line in name_status_raw.strip().split("\n"):
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                status_code = parts[0][0]
                file_path = parts[-1]
                if status_code == "M":
                    status_label, icon = "修改", "🟡"
                elif status_code == "A":
                    status_label, icon = "新增", "🔴"
                elif status_code == "D":
                    status_label, icon = "删除", "🔵"
                else:
                    status_label, icon = f"变更({status_code})", "⚪"
                file_list.append({
                    "status": status_code,
                    "status_label": status_label,
                    "icon": icon,
                    "file": file_path,
                })
        return file_list

    def _build_diff_info(
        self,
        target: Checkpoint,
        removed: List[Checkpoint],
        git_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        diff_info = {
            "reverted_files": [],
            "changed_files_raw": "",
            "stat_summary": "",
            "detailed_diff": "",
            "commits_being_reverted": "",
            "diff_audit": "",
        }

        if git_result.get("success"):
            diff_info["reverted_files"] = git_result.get("reverted_files", [])
            diff_info["changed_files_raw"] = git_result.get("changed_files_raw", "")
            diff_info["stat_summary"] = git_result.get("stat_summary", "")
            diff_info["detailed_diff"] = git_result.get("detailed_diff", "")
            diff_info["commits_being_reverted"] = git_result.get("commits_being_reverted", "")

        diff_audit_lines = []
        commits = diff_info["commits_being_reverted"]
        if commits:
            diff_audit_lines.append(f"📝 撤销的提交:\n{commits}")
        reverted_files = diff_info["reverted_files"]
        if reverted_files:
            diff_audit_lines.append("📂 撤销的文件变更:")
            for f in reverted_files:
                diff_audit_lines.append(f"  {f['icon']} {f['status_label']}  {f['file']}")
        elif diff_info["changed_files_raw"]:
            diff_audit_lines.append(f"📂 撤销的文件变更:\n{diff_info['changed_files_raw']}")
        elif diff_info["stat_summary"]:
            diff_audit_lines.append(f"📊 变更统计:\n{diff_info['stat_summary']}")
        else:
            if git_result.get("success"):
                diff_audit_lines.append("📂 Git 回退成功，但该轮次无物理文件变更（仅对话记忆回退）")
            elif target.git_commit:
                diff_audit_lines.append("📂 没有检测到物理文件的变更，系统仅回退了 Agent 的对话记忆")
            else:
                diff_audit_lines.append("📂 无 Git Commit 记录，仅回退了 Agent 的对话记忆")
        if diff_info["stat_summary"]:
            diff_audit_lines.append(f"📊 变更统计:\n{diff_info['stat_summary']}")

        diff_info["diff_audit"] = "\n".join(diff_audit_lines)
        return diff_info

    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT session_id, turn, timestamp, description, messages_json, git_commit, diff_stat, code_diff
                       FROM checkpoints WHERE session_id = ? ORDER BY turn ASC""",
                    (session_id,),
                ).fetchall()
            finally:
                conn.close()

        return [Checkpoint.from_row(r).to_dict() for r in rows]

    def preview_rollback(
        self,
        session_id: str,
        steps: int = 1,
        to_turn: Optional[int] = None,
        work_dir: str = "",
    ) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT session_id, turn, timestamp, description, messages_json, git_commit, diff_stat, code_diff
                       FROM checkpoints WHERE session_id = ? ORDER BY turn ASC""",
                    (session_id,),
                ).fetchall()

                if not rows:
                    return {"success": False, "error": "没有可用的检查点"}

                checkpoints = [Checkpoint.from_row(r) for r in rows]

                if to_turn is not None:
                    target_idx = next(
                        (i for i, cp in enumerate(checkpoints) if cp.turn == to_turn),
                        -1,
                    )
                    if target_idx == -1:
                        return {"success": False, "error": f"找不到第 {to_turn} 轮的检查点"}
                else:
                    target_idx = max(0, len(checkpoints) - steps)

                target_checkpoint = checkpoints[target_idx]
                removed_checkpoints = checkpoints[target_idx + 1:]

            finally:
                conn.close()

        diff_report = self._generate_diff_report(target_checkpoint, removed_checkpoints, work_dir)

        return {
            "success": True,
            "target_turn": target_checkpoint.turn,
            "target_timestamp": target_checkpoint.timestamp,
            "target_description": target_checkpoint.description,
            "target_git_commit": target_checkpoint.git_commit,
            "removed_turns": [cp.turn for cp in removed_checkpoints],
            "removed_descriptions": [cp.description for cp in removed_checkpoints],
            **diff_report,
        }

    def _generate_diff_report(
        self,
        target: Checkpoint,
        removed: List[Checkpoint],
        work_dir: str,
    ) -> Dict[str, Any]:
        result = {
            "reverted_files": [],
            "changed_files_raw": "",
            "stat_summary": "",
            "detailed_diff": "",
            "commits_being_reverted": "",
            "diff_report": "",
            "diff_lines": [],
        }

        if not target.git_commit or not work_dir or not os.path.exists(work_dir):
            result["diff_report"] = "📂 无 Git Commit 记录，回退仅影响 Agent 对话记忆"
            return result

        git_dir = os.path.join(work_dir, ".git")
        if not os.path.exists(git_dir):
            result["diff_report"] = "📂 工作目录不是 Git 仓库，回退仅影响 Agent 对话记忆"
            return result

        try:
            import subprocess

            stat_result = subprocess.run(
                ["git", "diff", "--stat", target.git_commit, "HEAD"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            result["stat_summary"] = stat_result.stdout.strip()

            name_status_result = subprocess.run(
                ["git", "diff", "--name-status", target.git_commit, "HEAD"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            result["changed_files_raw"] = name_status_result.stdout.strip()
            result["reverted_files"] = self._parse_changed_files(result["changed_files_raw"])

            detailed_result = subprocess.run(
                ["git", "diff", target.git_commit, "HEAD"],
                capture_output=True, text=True, timeout=30, cwd=work_dir,
            )
            raw_diff = detailed_result.stdout
            result["detailed_diff"] = raw_diff[:16000]
            result["diff_lines"] = self._parse_diff_to_lines(raw_diff)

            log_result = subprocess.run(
                ["git", "log", "--oneline", f"{target.git_commit}..HEAD"],
                capture_output=True, text=True, timeout=10, cwd=work_dir,
            )
            result["commits_being_reverted"] = log_result.stdout.strip()

            result["diff_report"] = self._build_markdown_diff_report(
                target, removed, result
            )

        except Exception as e:
            logger.error(f"生成 diff 报告异常: {e}")
            result["diff_report"] = f"❌ 生成 Diff 报告失败: {str(e)}"

        return result

    def _parse_diff_to_lines(self, raw_diff: str) -> List[Dict[str, Any]]:
        lines = []
        current_file = ""
        for line in raw_diff.split("\n"):
            if line.startswith("diff --git"):
                parts = line.split(" b/")
                if len(parts) >= 2:
                    current_file = parts[-1].strip()
            elif line.startswith("+++"):
                continue
            elif line.startswith("---"):
                continue
            elif line.startswith("@@"):
                lines.append({
                    "type": "header",
                    "file": current_file,
                    "content": line,
                })
            elif line.startswith("+"):
                lines.append({
                    "type": "ai_added",
                    "file": current_file,
                    "content": line[1:],
                })
            elif line.startswith("-"):
                lines.append({
                    "type": "ai_removed",
                    "file": current_file,
                    "content": line[1:],
                })
            elif line.startswith(" "):
                lines.append({
                    "type": "context",
                    "file": current_file,
                    "content": line[1:],
                })

        return lines[:2000]

    def _build_markdown_diff_report(
        self,
        target: Checkpoint,
        removed: List[Checkpoint],
        diff_data: Dict[str, Any],
    ) -> str:
        parts = []

        parts.append(f"## ⏪ 时光机回退预览\n")

        parts.append(f"**回退目标**: 第 {target.turn} 轮 ({target.description or '自动检查点'})")
        parts.append(f"**Git Commit**: `{target.git_commit[:8]}`\n")

        commits = diff_data.get("commits_being_reverted", "")
        if commits:
            parts.append("### 📝 将撤销的提交\n```")
            parts.append(commits)
            parts.append("```\n")

        reverted_files = diff_data.get("reverted_files", [])
        if reverted_files:
            parts.append("### 📂 将撤销的文件变更\n")
            for f in reverted_files:
                parts.append(f"- {f['icon']} **{f['status_label']}** `{f['file']}`")
            parts.append("")

        stat = diff_data.get("stat_summary", "")
        if stat:
            parts.append("### 📊 变更统计\n```")
            parts.append(stat)
            parts.append("```\n")

        detailed = diff_data.get("detailed_diff", "")
        if detailed:
            parts.append("### 🔍 代码差异详情\n```diff")
            parts.append(detailed[:8000])
            parts.append("```\n")

        return "\n".join(parts)

    def get_latest_commit(self, session_id: str) -> str:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT git_commit FROM checkpoints
                       WHERE session_id = ? AND git_commit != ''
                       ORDER BY turn DESC LIMIT 1""",
                    (session_id,),
                ).fetchone()
            finally:
                conn.close()

        return row[0] if row else ""

    def load_checkpoints(self, session_id: str):
        logger.info(f"已加载 {session_id} 的检查点（SQLite 按需查询）")

    def clear_checkpoints(self, session_id: str):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM checkpoints WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
            finally:
                conn.close()

        logger.info(f"已清除 {session_id} 的所有检查点")


_rewind_system: Optional[RewindSystem] = None


def get_rewind_system() -> RewindSystem:
    global _rewind_system
    if _rewind_system is None:
        _rewind_system = RewindSystem()
    return _rewind_system


REWIND_TOOL_DEFINITION_ANTHROPIC = {
    "name": "rewind_tool",
    "description": (
        "会话回退工具 - 时间机器功能，将系统恢复到之前的状态。"
        "action='create_checkpoint': 创建新的检查点"
        "action='rewind': 回退到指定轮数或步数"
        "action='list_checkpoints': 列出所有检查点"
        "action='clear_checkpoints': 清除所有检查点"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create_checkpoint", "rewind", "list_checkpoints", "clear_checkpoints"],
                "description": "操作类型",
            },
            "session_id": {
                "type": "string",
                "description": "会话 ID",
            },
            "steps": {
                "type": "integer",
                "description": "回退步数（默认 1）",
                "default": 1,
            },
            "to_turn": {
                "type": "integer",
                "description": "回退到指定轮数",
            },
            "description": {
                "type": "string",
                "description": "检查点描述",
            },
        },
        "required": ["action", "session_id"],
    },
}

REWIND_TOOL_DEFINITION_OPENAI = {
    "type": "function",
    "function": {
        "name": "rewind_tool",
        "description": (
            "会话回退工具 - 时间机器功能，将系统恢复到之前的状态。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_checkpoint", "rewind", "list_checkpoints", "clear_checkpoints"],
                    "description": "操作类型",
                },
                "session_id": {"type": "string", "description": "会话 ID"},
                "steps": {"type": "integer", "description": "回退步数"},
                "to_turn": {"type": "integer", "description": "回退到指定轮数"},
                "description": {"type": "string", "description": "检查点描述"},
            },
            "required": ["action", "session_id"],
        },
    },
}


def execute_rewind_tool(**kwargs) -> tuple[str, bool]:
    action = kwargs.get("action", "")
    session_id = kwargs.get("session_id", "")
    system = get_rewind_system()

    if not session_id:
        return "缺少必要参数: session_id", True

    if action == "create_checkpoint":
        try:
            from agent_runner import get_session_messages
            messages = get_session_messages(session_id) or []
            description = kwargs.get("description", "")
            system.create_checkpoint(session_id, len(messages) // 2, messages, description)
            return "✅ 检查点已创建", False
        except Exception as e:
            return f"创建检查点失败: {e}", True

    elif action == "rewind":
        steps = kwargs.get("steps", 1)
        to_turn = kwargs.get("to_turn")
        work_dir = kwargs.get("work_dir", "")
        result = system.rewind(session_id, steps, to_turn, work_dir=work_dir)
        if result["success"]:
            target = result.get("target_turn", 0)
            commit_short = result.get("git_commit", "")[:8]
            reverted = result.get("reverted_files", [])
            commits_reverted = result.get("commits_being_reverted", "")
            stat_summary = result.get("stat_summary", "")
            diff_audit = result.get("diff_audit", "")

            lines = [f"✅ 成功回退到第 {target} 轮"]
            if commit_short:
                lines.append(f"Git Commit: `{commit_short}`")
            if reverted:
                lines.append(f"📂 撤销了 {len(reverted)} 个物理文件:")
                for f in reverted[:8]:
                    lines.append(f"  {f['icon']} {f['status_label']}  `{f['file']}`")
                if len(reverted) > 8:
                    lines.append(f"  ... 还有 {len(reverted) - 8} 个文件")
            elif stat_summary:
                lines.append(f"📊 变更统计: {stat_summary}")
            else:
                lines.append("👻 未检测到物理文件修改，仅回退了 Agent 对话记忆")
            if commits_reverted:
                lines.append(f"📝 撤销的提交:\n{commits_reverted}")

            return "\n".join(lines), False
        else:
            return f"❌ 回退失败: {result.get('error', '未知错误')}", True

    elif action == "list_checkpoints":
        checkpoints = system.list_checkpoints(session_id)
        if not checkpoints:
            return "没有可用的检查点", False
        lines = [f"可用检查点 ({len(checkpoints)} 个):"]
        for cp in checkpoints:
            commit_short = cp.get("git_commit", "")[:8]
            commit_info = f" → {commit_short}" if commit_short else ""
            lines.append(
                f"  第 {cp['turn']} 轮: {cp['description'] or '自动检查点'}{commit_info}\n"
                f"    时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cp['timestamp']))}"
            )
        return "\n".join(lines), False

    elif action == "clear_checkpoints":
        system.clear_checkpoints(session_id)
        return "✅ 所有检查点已清除", False

    else:
        return f"未知操作: {action}", True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Eruitah 会话回退系统 v2 (Hybrid Pointer Architecture) 测试")
    print("=" * 60)

    system = get_rewind_system()
    session_id = "test_session"

    print("\n--- 创建检查点（无 Git） ---")
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]
    system.create_checkpoint(session_id, 1, messages, "初始状态")

    print("\n--- 创建检查点（带 Git Commit Hash） ---")
    messages2 = messages + [{"role": "user", "content": "Write code"}]
    system.create_checkpoint(
        session_id, 2, messages2, "代码已写完",
        git_commit="a3f7c2d1e4b5a6f7c8d9e0f1a2b3c4d5e6f7a8b9",
        diff_stat="2 files changed, 50 insertions(+), 10 deletions(-)",
    )

    print("\n--- 列出检查点 ---")
    checkpoints = system.list_checkpoints(session_id)
    for cp in checkpoints:
        commit = cp.get("git_commit", "")[:8]
        print(f"  第 {cp['turn']} 轮: {cp['description']} commit={commit}")

    print("\n--- 查询最新 Commit ---")
    latest = system.get_latest_commit(session_id)
    print(f"  最新 Commit: {latest[:8]}")

    print("\n--- 清除检查点 ---")
    system.clear_checkpoints(session_id)
    checkpoints = system.list_checkpoints(session_id)
    print(f"剩余检查点: {len(checkpoints)}")

    print("\n✅ 会话回退系统 v2 测试通过!")
