"""
Eruitah 智能编程沙盒 - 会话持久化 (Session Storage)

使用 SQLite 将 Agent 循环中的 messages 实时持久化落盘，
支持 /rewind 时光倒流功能。

数据库结构:
  - sessions: 会话表
  - messages: 消息表（每轮对话）
  - file_snapshots: 文件快照表（每次修改前的备份记录）

参考源码: claude-code-rev/src/utils/sessionStorage.ts
"""

import os
import json
import sqlite3
import time
import logging
import shutil
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".eruitah_cache")
DB_PATH = os.path.join(DB_DIR, "sessions.db")
BACKUP_DIR = os.path.join(DB_DIR, "backups")


def _ensure_dirs():
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)


class SessionStorage:
    """会话持久化管理器"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        _ensure_dirs()
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at REAL,
                work_dir TEXT,
                status TEXT DEFAULT 'active',
                task_name TEXT DEFAULT '',
                project_path TEXT DEFAULT ''
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                turn INTEGER,
                role TEXT,
                content TEXT,
                tool_calls TEXT,
                timestamp REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS file_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                turn INTEGER,
                file_path TEXT,
                backup_path TEXT,
                operation TEXT,
                timestamp REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                project_path TEXT,
                task_name TEXT,
                created_at REAL,
                updated_at REAL,
                status TEXT DEFAULT 'active',
                blackboard TEXT DEFAULT '{}',
                checkpoint_turn INTEGER DEFAULT 0
            )
        """)

        try:
            c.execute("ALTER TABLE sessions ADD COLUMN task_name TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE sessions ADD COLUMN project_path TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()

    def create_session(self, session_id: str, work_dir: str = ".") -> str:
        """创建新会话"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO sessions (id, created_at, work_dir, status) VALUES (?, ?, ?, ?)",
            (session_id, time.time(), work_dir, "active"),
        )
        conn.commit()
        conn.close()
        logger.info(f"创建会话: {session_id}")
        return session_id

    def save_message(self, session_id: str, turn: int, role: str, content: str, tool_calls: str = None):
        """保存一条消息"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO messages (session_id, turn, role, content, tool_calls, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn, role, content, tool_calls, time.time()),
        )
        conn.commit()
        conn.close()

    def save_messages_batch(self, session_id: str, turn: int, messages: list):
        """批量保存一轮的消息"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
            tool_calls = json.dumps(msg.get("tool_calls"), ensure_ascii=False) if msg.get("tool_calls") else None
            c.execute(
                "INSERT INTO messages (session_id, turn, role, content, tool_calls, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, turn, role, str(content), tool_calls, time.time()),
            )
        conn.commit()
        conn.close()

    def save_file_snapshot(self, session_id: str, turn: int, file_path: str, operation: str = "edit"):
        """
        保存文件快照（修改前备份）
        
        Args:
            session_id: 会话 ID
            turn: 当前轮次
            file_path: 被修改的文件路径
            operation: 操作类型 (edit/create)
        """
        if not os.path.exists(file_path):
            return None

        _ensure_dirs()

        backup_subdir = os.path.join(BACKUP_DIR, session_id, str(turn))
        os.makedirs(backup_subdir, exist_ok=True)

        safe_name = file_path.replace("/", "_").replace("\\", "_")
        backup_path = os.path.join(backup_subdir, safe_name)

        shutil.copy2(file_path, backup_path)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO file_snapshots (session_id, turn, file_path, backup_path, operation, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn, file_path, backup_path, operation, time.time()),
        )
        conn.commit()
        conn.close()

        logger.info(f"文件快照已保存: {file_path} -> {backup_path}")
        return backup_path

    def get_session_messages(self, session_id: str) -> list:
        """获取会话的所有消息"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT turn, role, content, tool_calls FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        rows = c.fetchall()
        conn.close()

        messages = []
        for row in rows:
            msg = {"role": row[1], "content": row[2]}
            if row[3]:
                try:
                    msg["tool_calls"] = json.loads(row[3])
                except json.JSONDecodeError:
                    pass
            messages.append(msg)
        return messages

    def get_latest_turn(self, session_id: str) -> int:
        """获取会话的最新轮次"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT MAX(turn) FROM messages WHERE session_id = ?",
            (session_id,),
        )
        row = c.fetchone()
        conn.close()
        return row[0] if row[0] else 0

    def get_file_snapshots(self, session_id: str, from_turn: int) -> list:
        """获取指定轮次之后的所有文件快照"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT turn, file_path, backup_path, operation FROM file_snapshots WHERE session_id = ? AND turn >= ? ORDER BY turn DESC",
            (session_id, from_turn),
        )
        rows = c.fetchall()
        conn.close()
        return [{"turn": r[0], "file_path": r[1], "backup_path": r[2], "operation": r[3]} for r in rows]

    def delete_messages_from_turn(self, session_id: str, from_turn: int):
        """删除指定轮次及之后的所有消息"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "DELETE FROM messages WHERE session_id = ? AND turn >= ?",
            (session_id, from_turn),
        )
        deleted = c.rowcount
        conn.commit()
        conn.close()
        logger.info(f"删除了 {deleted} 条消息 (从第 {from_turn} 轮开始)")
        return deleted

    def list_sessions(self) -> list:
        """列出所有会话"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id, created_at, work_dir, status, task_name, project_path FROM sessions ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "created_at": r[1], "work_dir": r[2], "status": r[3], "task_name": r[4] or "", "project_path": r[5] or ""} for r in rows]

    def create_task(self, task_id: str, project_path: str, task_name: str) -> str:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        now = time.time()
        c.execute(
            "INSERT INTO tasks (id, project_path, task_name, created_at, updated_at, status) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, project_path, task_name, now, now, "active"),
        )
        conn.commit()
        conn.close()
        logger.info(f"创建任务: {task_id} - {task_name}")
        return task_id

    def list_tasks(self, project_path: str = "") -> list:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if project_path:
            c.execute(
                "SELECT id, project_path, task_name, created_at, updated_at, status, blackboard FROM tasks WHERE project_path = ? AND status = 'active' ORDER BY updated_at DESC",
                (project_path,),
            )
        else:
            c.execute("SELECT id, project_path, task_name, created_at, updated_at, status, blackboard FROM tasks WHERE status = 'active' ORDER BY updated_at DESC")
        rows = c.fetchall()
        conn.close()
        result = []
        for r in rows:
            bb = {}
            try:
                bb = json.loads(r[6]) if r[6] else {}
            except (json.JSONDecodeError, TypeError):
                pass
            result.append({
                "id": r[0],
                "project_path": r[1],
                "task_name": r[2],
                "created_at": r[3],
                "updated_at": r[4],
                "status": r[5],
                "blackboard": bb,
            })
        return result

    def get_task(self, task_id: str) -> Optional[dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id, project_path, task_name, created_at, updated_at, status, blackboard FROM tasks WHERE id = ?", (task_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        bb = {}
        try:
            bb = json.loads(row[6]) if row[6] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        return {
            "id": row[0],
            "project_path": row[1],
            "task_name": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "status": row[5],
            "blackboard": bb,
        }

    def update_task_blackboard(self, task_id: str, blackboard: dict):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "UPDATE tasks SET blackboard = ?, updated_at = ? WHERE id = ?",
            (json.dumps(blackboard, ensure_ascii=False), time.time(), task_id),
        )
        conn.commit()
        conn.close()

    def update_task_status(self, task_id: str, status: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), task_id),
        )
        conn.commit()
        conn.close()

    def get_task_messages(self, task_id: str) -> list:
        return self.get_session_messages(task_id)

    def save_task_message(self, task_id: str, turn: int, role: str, content: str, tool_calls: str = None):
        self.save_message(task_id, turn, role, content, tool_calls)


# 全局单例
_storage: Optional[SessionStorage] = None


def get_storage() -> SessionStorage:
    global _storage
    if _storage is None:
        _storage = SessionStorage()
    return _storage
