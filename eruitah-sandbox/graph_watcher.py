"""
Eruitah 图谱守护者 - 实时文件监听与增量热更新

参考 codegraph 的增量同步理念，基于 watchdog 实现图谱的实时局部热更新。
当开发者保存代码文件时，守护者自动检测变更并触发单文件增量更新，
无需重新扫描整个项目。

用法:
    python graph_watcher.py [项目目录]

    如果不指定项目目录，默认使用当前工作目录。
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 监听的核心代码文件后缀
WATCHED_EXTENSIONS = {
    ".py", ".java", ".cpp", ".h", ".hpp", ".cc", ".cxx",
    ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".cs",
}

# 忽略的目录
IGNORED_DIRS = {
    ".git", "__pycache__", "node_modules", ".eruitah_cache",
    "dist", "build", ".venv", "venv", ".idea", ".vscode",
    "target", "bin", "obj", ".next", ".nuxt",
}

# 忽略的临时文件模式
IGNORED_PATTERNS = {
    ".tmp", ".swp", ".swo", "~", ".DS_Store",
}

# 防抖间隔（秒）
DEBOUNCE_SECONDS = 1.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("graph_watcher")


class CodeChangeHandler(FileSystemEventHandler):
    """
    代码文件变更处理器
    监听 on_modified 和 on_created 事件，触发增量图谱更新
    内置防抖机制，同一文件 1 秒内只触发一次更新
    """

    def __init__(self, project_dir: str):
        super().__init__()
        self.project_dir = os.path.abspath(project_dir)
        self.grapher = None
        self._last_update = {}  # { filepath: last_trigger_timestamp }
        self._lock = threading.Lock()
        self._pending = {}  # { filepath: timer }
        self._update_count = 0

    def _init_grapher(self):
        """懒加载 ProjectGrapher（首次变更时初始化）"""
        if self.grapher is not None:
            return True
        try:
            from project_grapher import ProjectGrapher
            logger.info("初始化图谱引擎...")
            self.grapher = ProjectGrapher(self.project_dir)
            # 先执行一次全量构建，建立符号表和文件索引
            self.grapher.run()
            logger.info("图谱引擎初始化完成，进入实时监听模式")
            return True
        except Exception as e:
            logger.error(f"图谱引擎初始化失败: {e}")
            self.grapher = None
            return False

    def _should_process(self, filepath: str) -> bool:
        """过滤机制：只处理核心代码文件，忽略噪声"""
        # 检查后缀
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in WATCHED_EXTENSIONS:
            return False

        # 检查路径中是否包含忽略目录
        parts = Path(filepath).parts
        for part in parts:
            if part in IGNORED_DIRS:
                return False

        # 检查临时文件
        basename = os.path.basename(filepath)
        for pattern in IGNORED_PATTERNS:
            if basename.endswith(pattern):
                return False

        return True

    def _debounced_update(self, filepath: str):
        """防抖更新：取消之前的定时器，重新计时"""
        with self._lock:
            # 取消之前的 pending timer
            if filepath in self._pending:
                self._pending[filepath].cancel()

            # 创建新的 timer
            timer = threading.Timer(
                DEBOUNCE_SECONDS,
                self._do_update,
                args=[filepath]
            )
            timer.daemon = True
            timer.start()
            self._pending[filepath] = timer

    def _do_update(self, filepath: str):
        """执行实际的增量更新"""
        with self._lock:
            self._pending.pop(filepath, None)

        if not self._init_grapher():
            return

        try:
            self.grapher.update_single_file(filepath)
            self._update_count += 1
            logger.info(f"📊 累计实时更新: {self._update_count} 次")
        except Exception as e:
            logger.error(f"增量更新失败 {filepath}: {e}")

    def on_modified(self, event):
        if event.is_directory:
            return
        filepath = os.path.abspath(event.src_path)
        if self._should_process(filepath):
            self._debounced_update(filepath)

    def on_created(self, event):
        if event.is_directory:
            return
        filepath = os.path.abspath(event.src_path)
        if self._should_process(filepath):
            self._debounced_update(filepath)


def main():
    project_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    project_dir = os.path.abspath(project_dir)

    if not os.path.isdir(project_dir):
        logger.error(f"目录不存在: {project_dir}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("  Eruitah 图谱守护者 v1.0")
    logger.info(f"  监听目录: {project_dir}")
    logger.info(f"  防抖间隔: {DEBOUNCE_SECONDS}s")
    logger.info(f"  监听后缀: {', '.join(sorted(WATCHED_EXTENSIONS))}")
    logger.info("=" * 60)

    handler = CodeChangeHandler(project_dir)
    observer = Observer()
    observer.schedule(handler, project_dir, recursive=True)
    observer.start()

    logger.info("[👁️ 守护者已上线] 正在监听代码变更，按 Ctrl+C 退出...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在停止守护者...")
        observer.stop()
        # 取消所有 pending timers
        with handler._lock:
            for timer in handler._pending.values():
                timer.cancel()
            handler._pending.clear()
        # 关闭数据库连接
        if handler.grapher:
            handler.grapher._db_close()

    observer.join()
    logger.info(f"守护者已离线，累计处理 {handler._update_count} 次实时更新")


if __name__ == "__main__":
    main()
