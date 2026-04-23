"""
Eruitah 智能编程沙盒 - /rewind 时光倒流命令

当 Agent 越改越乱时，用户可以输入 /rewind N 回到 N 步之前的状态。

核心流程:
  /rewind 3
      │
      ▼
  1. 从 SQLite 获取最近 3 轮的文件快照
  2. 将这 3 轮中被修改的文件从 .backup/ 恢复
  3. 删除 SQLite 中最近 3 轮的消息
  4. 返回恢复后的 messages 列表，Agent 从这里继续

参考源码: claude-code-rev/src/commands/rewind/rewind.ts
"""

import os
import shutil
import logging
from typing import Optional

from session_storage import SessionStorage, get_storage

logger = logging.getLogger(__name__)


class RewindResult:
    def __init__(self, success: bool, messages: list = None, 
                 restored_files: list = None, deleted_turns: int = 0,
                 error: str = None):
        self.success = success
        self.messages = messages or []
        self.restored_files = restored_files or []
        self.deleted_turns = deleted_turns
        self.error = error


def rewind(session_id: str, steps: int = 1) -> RewindResult:
    """
    时光倒流 - 回退 N 步

    Args:
        session_id: 会话 ID
        steps: 回退步数

    Returns:
        RewindResult: 包含恢复后的消息列表和恢复的文件列表
    """
    storage = get_storage()

    try:
        # 1. 获取当前最新轮次
        latest_turn = storage.get_latest_turn(session_id)
        if latest_turn == 0:
            return RewindResult(success=False, error="没有可回退的对话记录")

        # 计算回退到的轮次
        rewind_to_turn = max(1, latest_turn - steps + 1)

        # 2. 获取需要恢复的文件快照
        snapshots = storage.get_file_snapshots(session_id, rewind_to_turn)

        # 3. 恢复文件（从最新到最旧，确保恢复到最早的状态）
        restored_files = []
        restored_paths = set()

        for snapshot in snapshots:
            file_path = snapshot["file_path"]
            backup_path = snapshot["backup_path"]

            # 同一个文件只恢复最早的快照
            if file_path in restored_paths:
                continue

            if os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, file_path)
                    restored_files.append(file_path)
                    restored_paths.add(file_path)
                    logger.info(f"已恢复文件: {file_path}")
                except Exception as e:
                    logger.error(f"恢复文件失败: {file_path} -> {e}")

        # 4. 删除回退轮次及之后的消息
        deleted = storage.delete_messages_from_turn(session_id, rewind_to_turn)

        # 5. 获取恢复后的消息列表
        messages = storage.get_session_messages(session_id)

        logger.info(f"时光倒流完成: 回退 {steps} 步, 恢复 {len(restored_files)} 个文件, 删除 {deleted} 条消息")

        return RewindResult(
            success=True,
            messages=messages,
            restored_files=restored_files,
            deleted_turns=steps,
        )

    except Exception as e:
        logger.error(f"时光倒流失败: {e}")
        return RewindResult(success=False, error=str(e))


def format_rewind_result(result: RewindResult) -> str:
    """格式化回退结果为可读文本"""
    if not result.success:
        return f"❌ 回退失败: {result.error}"

    lines = [f"✅ 时光倒流成功! 回退了 {result.deleted_turns} 步"]

    if result.restored_files:
        lines.append(f"\n📁 已恢复的文件 ({len(result.restored_files)} 个):")
        for f in result.restored_files:
            lines.append(f"  - {f}")

    lines.append(f"\n💬 当前对话剩余 {len(result.messages)} 条消息")
    lines.append("Agent 将从回退后的状态继续执行。")

    return "\n".join(lines)
