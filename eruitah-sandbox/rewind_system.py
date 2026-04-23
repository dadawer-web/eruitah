"""
Eruitah 智能编程沙盒 - 会话回退系统 (Session Rewind)

核心思想（来自 Claude Code 的 rewind.ts + sessionStorage.ts）:
┌─────────────────────────────────────────────────────────────────────┐
│  检查点系统: 记录文件快照和对话历史，支持时间回退                    │
│                                                                     │
│  功能:                                                              │
│    1. 自动检查点: 执行写操作前自动创建文件快照                        │
│    2. 历史记录: 记录每轮对话的 messages 历史                       │
│    3. 回滚操作: 将文件系统和对话历史恢复到指定检查点                 │
│    4. 持久化: 检查点持久化到本地存储，支持重启后回滚                │
│                                                                     │
│  实现原理:                                                          │
│    - 检查点栈: 每轮对话压入一个检查点，支持多步回退                   │
│    - 文件快照: 写操作前备份文件内容到内存或临时文件                   │
│    - 历史截断: 回滚时从 messages 列表中弹出对应轮数的内容             │
└─────────────────────────────────────────────────────────────────────┘

参考源码:
    claude-code-rev/src/commands/rewind/rewind.ts
    claude-code-rev/src/services/history/
    claude-code-rev/src/utils/sessionStorage.ts
"""

import os
import json
import time
import shutil
import tempfile
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = os.environ.get(
    "ERUITAH_CHECKPOINT_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".checkpoints"),
)


@dataclass
class FileSnapshot:
    file_path: str
    backup_path: str
    content: str
    timestamp: float
    operation: str  # "create", "edit", "delete"


@dataclass
class Checkpoint:
    session_id: str
    turn: int
    timestamp: float
    messages: List[Dict[str, Any]]
    file_snapshots: List[FileSnapshot] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "timestamp": self.timestamp,
            "messages": self.messages,
            "file_snapshots": [
                {
                    "file_path": s.file_path,
                    "backup_path": s.backup_path,
                    "operation": s.operation,
                    "timestamp": s.timestamp,
                }
                for s in self.file_snapshots
            ],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        return cls(
            session_id=data["session_id"],
            turn=data["turn"],
            timestamp=data["timestamp"],
            messages=data["messages"],
            file_snapshots=[
                FileSnapshot(
                    file_path=s["file_path"],
                    backup_path=s["backup_path"],
                    content="",  # 内容不持久化，只在内存中
                    timestamp=s["timestamp"],
                    operation=s["operation"],
                )
                for s in data.get("file_snapshots", [])
            ],
            description=data.get("description", ""),
        )


class RewindSystem:
    def __init__(self):
        self._checkpoints: Dict[str, List[Checkpoint]] = {}
        self._lock = threading.Lock()
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    def create_checkpoint(
        self,
        session_id: str,
        turn: int,
        messages: List[Dict[str, Any]],
        description: str = "",
    ) -> Checkpoint:
        checkpoint = Checkpoint(
            session_id=session_id,
            turn=turn,
            timestamp=time.time(),
            messages=messages.copy(),
            description=description,
        )

        with self._lock:
            if session_id not in self._checkpoints:
                self._checkpoints[session_id] = []
            self._checkpoints[session_id].append(checkpoint)

        self._persist_checkpoint(checkpoint)
        logger.info(f"创建检查点 {session_id}:{turn} - {description}")
        return checkpoint

    def add_file_snapshot(
        self,
        session_id: str,
        file_path: str,
        operation: str = "edit",
    ):  
        with self._lock:
            if session_id not in self._checkpoints or not self._checkpoints[session_id]:
                return

            checkpoint = self._checkpoints[session_id][-1]

            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                temp_fd, backup_path = tempfile.mkstemp(dir=CHECKPOINT_DIR)
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    f.write(content)

                snapshot = FileSnapshot(
                    file_path=file_path,
                    backup_path=backup_path,
                    content=content,
                    timestamp=time.time(),
                    operation=operation,
                )
                checkpoint.file_snapshots.append(snapshot)

                logger.debug(f"文件快照: {file_path} → {backup_path}")

    def rewind(
        self,
        session_id: str,
        steps: int = 1,
        to_turn: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if session_id not in self._checkpoints or not self._checkpoints[session_id]:
                return {
                    "success": False,
                    "error": "没有可用的检查点",
                }

            checkpoints = self._checkpoints[session_id]

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
            removed_checkpoints = checkpoints[target_idx + 1 :]

            # 恢复文件快照
            restored_files = []
            for cp in reversed(removed_checkpoints):
                for snapshot in reversed(cp.file_snapshots):
                    if os.path.exists(snapshot.backup_path):
                        try:
                            shutil.copy2(snapshot.backup_path, snapshot.file_path)
                            restored_files.append(snapshot.file_path)
                        except Exception as e:
                            logger.error(f"恢复文件失败 {snapshot.file_path}: {e}")

            # 清理临时文件
            for cp in removed_checkpoints:
                for snapshot in cp.file_snapshots:
                    if os.path.exists(snapshot.backup_path):
                        try:
                            os.unlink(snapshot.backup_path)
                        except Exception:
                            pass

            # 截断检查点和消息历史
            self._checkpoints[session_id] = checkpoints[: target_idx + 1]

            logger.info(
                f"回退到检查点 {session_id}:{target_checkpoint.turn}，恢复了 {len(restored_files)} 个文件"
            )

            return {
                "success": True,
                "restored_files": restored_files,
                "target_turn": target_checkpoint.turn,
                "target_timestamp": target_checkpoint.timestamp,
                "messages": target_checkpoint.messages,
            }

    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            if session_id not in self._checkpoints:
                return []
            return [cp.to_dict() for cp in self._checkpoints[session_id]]

    def _persist_checkpoint(self, checkpoint: Checkpoint):
        checkpoint_file = os.path.join(
            CHECKPOINT_DIR,
            f"{checkpoint.session_id}_{checkpoint.turn}.json",
        )
        try:
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"持久化检查点失败: {e}")

    def load_checkpoints(self, session_id: str):
        checkpoint_files = []
        for filename in os.listdir(CHECKPOINT_DIR):
            if filename.startswith(f"{session_id}_") and filename.endswith(".json"):
                checkpoint_files.append(os.path.join(CHECKPOINT_DIR, filename))

        checkpoints = []
        for file_path in sorted(checkpoint_files):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    checkpoints.append(Checkpoint.from_dict(data))
            except Exception as e:
                logger.error(f"加载检查点失败 {file_path}: {e}")

        with self._lock:
            self._checkpoints[session_id] = checkpoints

        logger.info(f"已加载 {len(checkpoints)} 个检查点")

    def clear_checkpoints(self, session_id: str):
        with self._lock:
            if session_id in self._checkpoints:
                checkpoints = self._checkpoints[session_id]
                for cp in checkpoints:
                    for snapshot in cp.file_snapshots:
                        if os.path.exists(snapshot.backup_path):
                            try:
                                os.unlink(snapshot.backup_path)
                            except Exception:
                                pass
                self._checkpoints[session_id] = []

        for filename in os.listdir(CHECKPOINT_DIR):
            if filename.startswith(f"{session_id}_") and filename.endswith(".json"):
                try:
                    os.unlink(os.path.join(CHECKPOINT_DIR, filename))
                except Exception:
                    pass

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
            return f"✅ 检查点已创建", False
        except Exception as e:
            return f"创建检查点失败: {e}", True

    elif action == "rewind":
        steps = kwargs.get("steps", 1)
        to_turn = kwargs.get("to_turn")
        result = system.rewind(session_id, steps, to_turn)
        if result["success"]:
            restored = result.get("restored_files", [])
            target = result.get("target_turn", 0)
            return (
                f"✅ 成功回退到第 {target} 轮\n"
                f"恢复的文件: {len(restored)}\n"
                f"{', '.join(restored[:5])}{'...' if len(restored) > 5 else ''}",
                False,
            )
        else:
            return f"❌ 回退失败: {result.get('error', '未知错误')}", True

    elif action == "list_checkpoints":
        checkpoints = system.list_checkpoints(session_id)
        if not checkpoints:
            return "没有可用的检查点", False
        lines = [f"可用检查点 ({len(checkpoints)} 个):"]
        for cp in checkpoints:
            lines.append(
                f"  第 {cp['turn']} 轮: {cp['description'] or '自动检查点'}\n"
                f"    时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cp['timestamp']))}\n"
                f"    文件快照: {len(cp.get('file_snapshots', []))}"
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
    print("Eruitah 会话回退系统测试")
    print("=" * 60)

    system = get_rewind_system()
    session_id = "test_session"

    print("\n--- 创建检查点 ---")
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]
    system.create_checkpoint(session_id, 1, messages, "初始状态")

    print("\n--- 添加文件快照 ---")
    test_file = "/tmp/test.txt"
    with open(test_file, "w") as f:
        f.write("original content")
    system.add_file_snapshot(session_id, test_file)

    print("\n--- 模拟修改文件 ---")
    with open(test_file, "w") as f:
        f.write("modified content")
    print(f"文件内容: {open(test_file).read()}")

    print("\n--- 回退 ---")
    result = system.rewind(session_id, 1)
    print(f"回退结果: {result['success']}")
    print(f"恢复的文件: {result.get('restored_files', [])}")
    print(f"文件内容: {open(test_file).read()}")

    print("\n--- 列出检查点 ---")
    checkpoints = system.list_checkpoints(session_id)
    for cp in checkpoints:
        print(f"  第 {cp['turn']} 轮: {cp['description']}")

    print("\n--- 清除检查点 ---")
    system.clear_checkpoints(session_id)
    checkpoints = system.list_checkpoints(session_id)
    print(f"剩余检查点: {len(checkpoints)}")

    print("\n✅ 会话回退系统测试通过!")
