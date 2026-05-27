"""
Eruitah 智能编程沙盒 - GitSandboxManager v3 (WarmPool 预热池架构)

核心升级:
  v1: git checkout -b → 单目录切换，多 Agent 并发时交叉污染
  v2: git worktree add → 绝对物理隔离，每个任务独占一个物理目录
  v3: WarmPool 预热池 → 后台预建 worktree，新任务 O(1) 极速分配

架构:
  主仓库 (workspace_dir) ── 永远停留在 master/main 分支
    ├── .git/
    └── agent-worktrees/         ← 与主仓库同级
        ├── task_abc123/         ← 任务 A 的专属物理目录 (独立分支 task/task_abc123)
        ├── task_def456/         ← 任务 B 的专属物理目录 (独立分支 task/task_def456)
        ├── warmup_a1b2/        ← 预热池中的待命 worktree (分支 warmup/a1b2)
        ├── warmup_c3d4/        ← 预热池中的待命 worktree (分支 warmup/c3d4)
        └── warmup_e5f6/        ← 预热池中的待命 worktree (分支 warmup/e5f6)

WarmPool 机制:
  后台守护线程持续维护 pool_size=3 的预热池。
  新任务到来时，直接 pop 预热好的 worktree，重命名分支即可，耗时 ~0ms。
  缓存击穿时降级为同步创建 (Slow Path)。

三级回退:
  L1: rollback_task_step → git reset --hard HEAD~N (worktree 内)
  L2: remove_task_workspace → git worktree remove + branch -D
  L3: revert_merged_task → git revert -m 1 <merge_commit> (主仓库)
"""

import os
import uuid
import subprocess
import logging
import threading
import time
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

WARMUP_BRANCH_PREFIX = "warmup/"
TASK_BRANCH_PREFIX = "task/"

BASE_REPO_DIR = os.environ.get(
    "ERUITAH_BASE_REPO", os.path.join(os.path.expanduser("~"), "eruitah_base_repo")
)
WORKTREES_ROOT = os.environ.get(
    "ERUITAH_WORKTREES_ROOT", os.path.join(os.path.expanduser("~"), "agent-worktrees")
)


def _validate_path_not_protected(path: str) -> bool:
    abs_path = os.path.abspath(path)
    protected = [
        os.path.abspath(BASE_REPO_DIR),
        os.path.abspath(WORKTREES_ROOT),
        os.path.expanduser("~"),
        "/",
    ]
    for p in protected:
        if abs_path == p:
            return False
        if abs_path.startswith(p) and abs_path == p:
            return False
    return True


class GitSandboxManager:
    def __init__(self, base_repo_dir: Optional[str] = None, worktrees_root: Optional[str] = None, pool_size: int = 3):
        self.workspace_dir = os.path.abspath(base_repo_dir or BASE_REPO_DIR)
        self.worktree_base = os.path.abspath(worktrees_root or WORKTREES_ROOT)

        if self.workspace_dir == self.worktree_base:
            raise ValueError(
                f"BASE_REPO_DIR 和 WORKTREES_ROOT 不能相同: {self.workspace_dir}"
            )

        if self.worktree_base.startswith(self.workspace_dir + os.sep):
            raise ValueError(
                f"WORKTREES_ROOT 不能是 BASE_REPO_DIR 的子目录! "
                f"BASE_REPO_DIR={self.workspace_dir}, WORKTREES_ROOT={self.worktree_base}"
            )

        self._worktrees: Dict[str, str] = {}
        self._pool_size = pool_size
        self._warm_pool: List[Dict[str, str]] = []
        self._pool_lock = threading.Lock()
        self._pool_maintainer_stop = threading.Event()

        self._init_repo()
        self._discover_worktrees()
        self._cleanup_stale_warmups()
        self._start_pool_maintainer()

        logger.info(
            f"🏗️ GitSandboxManager 初始化完毕\n"
            f"  BASE_REPO_DIR: {self.workspace_dir}\n"
            f"  WORKTREES_ROOT: {self.worktree_base}\n"
            f"  Pool Size: {self._pool_size}"
        )

    def _run_git(
        self, *args, cwd: Optional[str] = None, check: bool = False
    ) -> subprocess.CompletedProcess:
        target_dir = cwd or self.workspace_dir
        cmd = ["git"] + list(args)
        try:
            result = subprocess.run(
                cmd,
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0 and check:
                logger.error(f"Git failed: {' '.join(cmd)}\n{result.stderr.strip()}")
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"Git timeout: {' '.join(cmd)}")
            return subprocess.CompletedProcess(cmd, 1, "", "timeout")
        except Exception as e:
            logger.error(f"Git exception: {e}")
            return subprocess.CompletedProcess(cmd, 1, "", str(e))

    def _run_git_ok(self, *args, cwd: Optional[str] = None) -> bool:
        return self._run_git(*args, cwd=cwd).returncode == 0

    def _init_repo(self):
        if not os.path.exists(self.workspace_dir):
            os.makedirs(self.workspace_dir, exist_ok=True)

        git_dir = os.path.join(self.workspace_dir, ".git")
        if not os.path.exists(git_dir):
            logger.info(f"🔧 初始化 Git 仓库: {self.workspace_dir}")
            self._run_git("init")
            self._run_git("config", "user.email", "eruitah@sandbox.local")
            self._run_git("config", "user.name", "Eruitah Sandbox")

            gitignore_path = os.path.join(self.workspace_dir, ".gitignore")
            if not os.path.exists(gitignore_path):
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write(
                        "\n".join(
                            [
                                "node_modules/",
                                "__pycache__/",
                                ".git/",
                                "venv/",
                                ".venv/",
                                "dist/",
                                "build/",
                                ".next/",
                                ".nuxt/",
                                "target/",
                                ".gradle/",
                                ".eruitah_snapshots/",
                                ".checkpoints/",
                                ".eruitah_cache/",
                                ".tasks/",
                                "agent-worktrees/",
                            ]
                        )
                        + "\n"
                    )
                self._run_git("add", ".gitignore")

            has_files = self._run_git("diff", "--cached", "--name-only")
            if has_files.stdout.strip() or self._has_untracked_files():
                self._run_git("add", ".")
                self._run_git(
                    "commit", "-m", "Base system initialized", "--allow-empty"
                )
                logger.info("✅ 物理沙盒 Git 引擎初始化完毕")
            else:
                self._run_git(
                    "commit", "-m", "Base system initialized", "--allow-empty"
                )
                logger.info("✅ 物理沙盒 Git 引擎初始化完毕（空仓库）")
        else:
            self._run_git("config", "user.email", "eruitah@sandbox.local")
            self._run_git("config", "user.name", "Eruitah Sandbox")

            gitignore_path = os.path.join(self.workspace_dir, ".gitignore")
            if os.path.exists(gitignore_path):
                try:
                    with open(gitignore_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if "agent-worktrees/" not in content:
                        with open(gitignore_path, "a", encoding="utf-8") as f:
                            f.write("\nagent-worktrees/\n")
                        logger.info("📝 已追加 agent-worktrees/ 到 .gitignore")
                except Exception as e:
                    logger.warning(f"⚠️ 更新 .gitignore 失败: {e}")

            logger.info(
                f"Git 仓库已存在，当前分支: {self._get_current_branch()}"
            )

    @staticmethod
    def _strip_ref_prefix(branch_ref: str) -> str:
        if branch_ref.startswith("refs/heads/"):
            return branch_ref[len("refs/heads/"):]
        return branch_ref

    def _discover_worktrees(self):
        result = self._run_git("worktree", "list", "--porcelain")
        if result.returncode != 0:
            return

        current_path = None
        current_branch = None
        for line in result.stdout.strip().split("\n"):
            if line.startswith("worktree "):
                current_path = line[len("worktree "):]
            elif line.startswith("branch "):
                current_branch = self._strip_ref_prefix(line[len("branch "):])
                if current_branch.startswith(TASK_BRANCH_PREFIX) and current_path:
                    task_id = current_branch[len(TASK_BRANCH_PREFIX):]
                    if os.path.exists(current_path):
                        self._worktrees[task_id] = current_path
                        logger.info(
                            f"🌿 发现已有 worktree: 任务 {task_id} → {current_path}"
                        )
                current_path = None
                current_branch = None

    def _cleanup_stale_warmups(self):
        result = self._run_git("worktree", "list", "--porcelain")
        if result.returncode != 0:
            return

        current_path = None
        current_branch = None
        for line in result.stdout.strip().split("\n"):
            if line.startswith("worktree "):
                current_path = line[len("worktree "):]
            elif line.startswith("branch "):
                current_branch = self._strip_ref_prefix(line[len("branch "):])
                if current_branch and current_branch.startswith(WARMUP_BRANCH_PREFIX) and current_path:
                    warmup_id = current_branch[len(WARMUP_BRANCH_PREFIX):]
                    logger.info(f"🧹 清理残留预热 worktree: {warmup_id}")
                    if os.path.exists(current_path):
                        self._run_git_ok("worktree", "remove", current_path, "--force")
                    if self._branch_exists(current_branch):
                        self._run_git_ok("branch", "-D", current_branch)
                current_path = None
                current_branch = None

        self._run_git_ok("worktree", "prune")

    def _start_pool_maintainer(self):
        t = threading.Thread(target=self._maintain_pool, daemon=True)
        t.start()
        logger.info(f"🏊 WarmPool 预热池守护线程已启动 (目标池大小: {self._pool_size})")

    def _maintain_pool(self):
        consecutive_failures = 0
        while not self._pool_maintainer_stop.is_set():
            with self._pool_lock:
                current_size = len(self._warm_pool)

            if current_size < self._pool_size:
                ok = self._create_warmup_entry()
                if ok:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

            wait_time = 5 + min(consecutive_failures * 10, 60)
            self._pool_maintainer_stop.wait(wait_time)

    def _create_warmup_entry(self) -> bool:
        warmup_id = uuid.uuid4().hex[:8]
        warmup_branch = f"{WARMUP_BRANCH_PREFIX}{warmup_id}"
        warmup_dir = os.path.abspath(os.path.join(self.worktree_base, f"warmup_{warmup_id}"))

        os.makedirs(self.worktree_base, exist_ok=True)

        main_branch = self._get_main_branch()

        result = self._run_git(
            "worktree", "add", warmup_dir, "-b", warmup_branch, main_branch
        )

        if result.returncode == 0:
            entry = {
                "warmup_id": warmup_id,
                "warmup_branch": warmup_branch,
                "warmup_dir": warmup_dir,
            }
            with self._pool_lock:
                self._warm_pool.append(entry)
            logger.info(
                f"🏊 预热池新增: {warmup_id} → {warmup_dir} "
                f"(池中: {len(self._warm_pool)}/{self._pool_size})"
            )
            return True
        else:
            logger.warning(
                f"⚠️ 预热 worktree 创建失败: {warmup_id} "
                f"原因: {result.stderr.strip()[:200]}"
            )
            if os.path.exists(warmup_dir):
                import shutil
                shutil.rmtree(warmup_dir, ignore_errors=True)
            self._run_git_ok("worktree", "prune")
            if self._branch_exists(warmup_branch):
                self._run_git_ok("branch", "-D", warmup_branch)
            return False

    def _has_untracked_files(self) -> bool:
        result = self._run_git("ls-files", "--others", "--exclude-standard")
        return bool(result.stdout.strip())

    def _get_current_branch(self) -> str:
        result = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if result.returncode == 0:
            return result.stdout.strip()
        return "master"

    def _get_main_branch(self) -> str:
        for candidate in ["main", "master"]:
            if self._branch_exists(candidate):
                return candidate
        result = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if result.returncode == 0:
            return result.stdout.strip()
        return "master"

    def _branch_exists(self, branch_name: str) -> bool:
        result = self._run_git("branch", "--list", branch_name)
        return bool(result.stdout.strip())

    def _get_worktree_dir(self, task_id: str, user_id: int = 0, session_id: str = "") -> str:
        if user_id and session_id:
            from sandbox_isolation import get_user_work_dir
            return os.path.abspath(get_user_work_dir(user_id, session_id))
        return os.path.abspath(os.path.join(self.worktree_base, task_id))

    def get_worktree_path(self, task_id: str, user_id: int = 0, session_id: str = "") -> str:
        if task_id in self._worktrees:
            return self._worktrees[task_id]
        task_dir = self._get_worktree_dir(task_id, user_id, session_id)
        if os.path.exists(task_dir) and os.path.exists(
            os.path.join(task_dir, ".git")
        ):
            self._worktrees[task_id] = task_dir
            return task_dir
        return self.workspace_dir

    def _fix_worktree_gitdir(self, worktree_dir: str, old_branch: str, new_branch: str):
        git_file = os.path.join(worktree_dir, ".git")
        if not os.path.exists(git_file):
            return

        try:
            with open(git_file, "r") as f:
                content = f.read().strip()

            if content.startswith("gitdir: "):
                old_gitdir = content[len("gitdir: "):]
                old_admin_dir = old_gitdir

                if os.path.basename(old_admin_dir) == old_branch.replace("/", "_") or \
                   old_branch.replace("/", "_") in old_admin_dir:
                    new_admin_dir = os.path.join(
                        os.path.dirname(old_admin_dir),
                        new_branch.replace("/", "_")
                    )

                    if os.path.exists(old_admin_dir) and not os.path.exists(new_admin_dir):
                        import shutil
                        shutil.move(old_admin_dir, new_admin_dir)
                        logger.info(
                            f"🔧 Git admin 目录重命名: {os.path.basename(old_admin_dir)} → {os.path.basename(new_admin_dir)}"
                        )

                    with open(git_file, "w") as f:
                        f.write(f"gitdir: {new_admin_dir}\n")

                    head_file = os.path.join(new_admin_dir, "HEAD")
                    if os.path.exists(head_file):
                        with open(head_file, "w") as f:
                            f.write(f"ref: refs/heads/{new_branch}\n")

        except Exception as e:
            logger.warning(f"⚠️ 修复 worktree gitdir 失败: {e}")

    def create_task_workspace(self, task_id: str, base_task_id: str = "", user_id: int = 0, session_id: str = "") -> str:
        safe_branch = f"{TASK_BRANCH_PREFIX}{task_id}"
        task_dir = self._get_worktree_dir(task_id, user_id=user_id, session_id=session_id)

        if task_id in self._worktrees and os.path.exists(self._worktrees[task_id]):
            logger.info(f"🌿 任务 {task_id} 的 worktree 已存在: {self._worktrees[task_id]}")
            return self._worktrees[task_id]

        os.makedirs(os.path.dirname(task_dir), exist_ok=True)
        os.makedirs(self.worktree_base, exist_ok=True)

        if base_task_id:
            return self._create_workspace_slow(task_id, task_dir, safe_branch, base_task_id)

        entry = None
        pool_remaining = 0
        with self._pool_lock:
            if self._warm_pool:
                entry = self._warm_pool.pop(0)
                pool_remaining = len(self._warm_pool)

        if entry:
            warmup_branch = entry["warmup_branch"]
            warmup_dir = entry["warmup_dir"]

            self._run_git_ok("worktree", "remove", warmup_dir, "--force")
            if self._branch_exists(warmup_branch):
                self._run_git_ok("branch", "-m", warmup_branch, safe_branch)

            if self._branch_exists(safe_branch):
                add_result = self._run_git(
                    "worktree", "add", task_dir, safe_branch
                )
                if add_result.returncode == 0:
                    main_branch = self._get_main_branch()
                    self._run_git_ok("reset", "--hard", main_branch, cwd=task_dir)

                    self._run_git("add", ".", cwd=self.workspace_dir)
                    status = self._run_git("status", "--porcelain", cwd=self.workspace_dir)
                    if status.stdout.strip():
                        self._run_git(
                            "commit",
                            "-m",
                            f"Auto-save before task {task_id}",
                            "--allow-empty",
                            cwd=self.workspace_dir,
                        )
                        self._run_git_ok("reset", "--hard", main_branch, cwd=task_dir)

                    self._worktrees[task_id] = task_dir
                    logger.info(
                        f"⚡ [Fast Path] 任务 {task_id} 从预热池极速分配！"
                        f"(池中剩余: {pool_remaining}/{self._pool_size})"
                    )
                    return task_dir

            logger.warning(f"⚠️ Fast Path 分配失败，降级为 Slow Path")
            if self._branch_exists(safe_branch):
                self._run_git_ok("branch", "-D", safe_branch)

        return self._create_workspace_slow(task_id, task_dir, safe_branch, base_task_id)

    def _create_workspace_slow(
        self, task_id: str, task_dir: str, safe_branch: str, base_task_id: str = ""
    ) -> str:
        logger.info(f"🐌 [Slow Path] 为任务 {task_id} 同步创建 worktree...")

        if self._branch_exists(safe_branch):
            success = self._run_git_ok("worktree", "add", task_dir, safe_branch)
        else:
            self._run_git("add", ".", cwd=self.workspace_dir)
            status = self._run_git("status", "--porcelain", cwd=self.workspace_dir)
            if status.stdout.strip():
                self._run_git(
                    "commit",
                    "-m",
                    f"Auto-save before task {task_id}",
                    "--allow-empty",
                    cwd=self.workspace_dir,
                )

            if base_task_id:
                base_branch = f"{TASK_BRANCH_PREFIX}{base_task_id}"
                if self._branch_exists(base_branch):
                    success = self._run_git_ok(
                        "worktree", "add", task_dir, "-b", safe_branch, base_branch
                    )
                    if success:
                        logger.info(f"🔗 任务 {task_id} 基于任务 {base_task_id} 创建 (链式依赖)")
                else:
                    logger.warning(f"⚠️ 基底任务分支 {base_branch} 不存在，回退到主分支")
                    success = self._run_git_ok(
                        "worktree", "add", task_dir, "-b", safe_branch
                    )
            else:
                success = self._run_git_ok(
                    "worktree", "add", task_dir, "-b", safe_branch
                )

        if success:
            self._worktrees[task_id] = task_dir
            logger.info(f"🌿 任务 {task_id} 的专属物理工作区已挂载: {task_dir}")
            return task_dir
        else:
            logger.error(f"❌ 创建 worktree 失败: {task_id}，回退到主仓库")
            self._worktrees[task_id] = self.workspace_dir
            return self.workspace_dir

    def switch_to_task(self, task_id: str) -> str:
        if task_id in self._worktrees and os.path.exists(self._worktrees[task_id]):
            return self._worktrees[task_id]

        task_dir = self._get_worktree_dir(task_id)
        if os.path.exists(task_dir):
            self._worktrees[task_id] = task_dir
            return task_dir

        return self.create_task_workspace(task_id)

    def commit_agent_changes(self, task_id: str, summary: str = "Agent auto-update", model_name: str = "unknown") -> str:
        task_dir = self._worktrees.get(task_id) or self._get_worktree_dir(task_id)
        if not os.path.exists(task_dir):
            logger.warning(f"任务 {task_id} 的 worktree 不存在，跳过提交")
            return ""

        add_result = self._run_git("add", ".", cwd=task_dir)
        if add_result.returncode != 0:
            logger.warning(f"⚠️ git add 失败 (cwd={task_dir}): {add_result.stderr.strip()[:150]}")

        status = self._run_git("status", "--porcelain", cwd=task_dir)
        if not status.stdout.strip():
            rev_result = self._run_git("rev-parse", "HEAD", cwd=task_dir)
            return rev_result.stdout.strip() if rev_result.returncode == 0 else ""

        commit_message = (
            f"feat(agent): {summary}\n\n"
            f"Agent-Task: {task_id}\n"
            f"Agent-Model: {model_name}\n"
            f"Agent-Decision: Auto-checkpoint via sandbox"
        )

        commit_result = self._run_git("commit", "-m", commit_message, cwd=task_dir)
        if commit_result.returncode == 0:
            rev_result = self._run_git("rev-parse", "HEAD", cwd=task_dir)
            commit_hash = rev_result.stdout.strip() if rev_result.returncode == 0 else ""
            logger.info(f"💾 任务 {task_id} 已物理存档: {summary[:50]} commit={commit_hash[:8]}")
            return commit_hash
        else:
            logger.error(
                f"❌ 任务 {task_id} auto-commit 失败!\n"
                f"  cwd: {task_dir}\n"
                f"  stderr: {commit_result.stderr.strip()[:200]}"
            )
            return ""

    def _verify_rollback_dir(self, task_id: str) -> Optional[str]:
        task_dir = self._worktrees.get(task_id) or self._get_worktree_dir(task_id)
        if not os.path.exists(task_dir):
            logger.error(f"❌ 回退失败: 任务 {task_id} 的 worktree 目录不存在: {task_dir}")
            return None

        git_check = os.path.exists(os.path.join(task_dir, ".git"))
        if not git_check:
            logger.error(f"❌ 回退失败: {task_dir} 不是有效的 Git 工作区")
            return None

        return task_dir

    def _capture_pre_rollback_diff(self, target: str, cwd: str) -> Dict[str, Any]:
        diff_stat = self._run_git("diff", target, "HEAD", "--name-status", cwd=cwd)
        changed_files_raw = diff_stat.stdout.strip()

        diff_stat_summary = self._run_git("diff", target, "HEAD", "--stat", cwd=cwd)
        stat_summary = diff_stat_summary.stdout.strip()

        detailed_diff = ""
        full_diff_result = self._run_git("diff", target, "HEAD", cwd=cwd)
        if full_diff_result.returncode == 0:
            detailed_diff = full_diff_result.stdout[:8000]

        log_range = self._run_git("log", "--oneline", f"{target}..HEAD", cwd=cwd)
        commits_being_reverted = log_range.stdout.strip()

        untracked = self._run_git("ls-files", "--others", "--exclude-standard", cwd=cwd)
        untracked_files = untracked.stdout.strip()

        file_list = []
        if changed_files_raw:
            for line in changed_files_raw.split("\n"):
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    status_code = parts[0][0]
                    file_path = parts[-1]
                    if status_code == "M":
                        status_label = "修改"
                        icon = "🟡"
                    elif status_code == "A":
                        status_label = "新增"
                        icon = "🔴"
                    elif status_code == "D":
                        status_label = "删除"
                        icon = "🔵"
                    else:
                        status_label = f"变更({status_code})"
                        icon = "⚪"
                    file_list.append({
                        "status": status_code,
                        "status_label": status_label,
                        "icon": icon,
                        "file": file_path,
                    })

        return {
            "changed_files_raw": changed_files_raw,
            "file_list": file_list,
            "stat_summary": stat_summary,
            "detailed_diff": detailed_diff,
            "commits_being_reverted": commits_being_reverted,
            "untracked_files": untracked_files,
        }

    def _hard_reset_with_clean(self, target: str, cwd: str) -> bool:
        reset_result = self._run_git("reset", "--hard", target, cwd=cwd)
        if reset_result.returncode != 0:
            logger.error(
                f"❌ git reset --hard {target} 失败!\n"
                f"  cwd: {cwd}\n"
                f"  stderr: {reset_result.stderr.strip()[:300]}"
            )
            return False

        clean_result = self._run_git("clean", "-fd", cwd=cwd)
        if clean_result.returncode != 0:
            logger.warning(
                f"⚠️ git clean -fd 失败 (非致命):\n"
                f"  cwd: {cwd}\n"
                f"  stderr: {clean_result.stderr.strip()[:200]}"
            )

        logger.info(
            f"✅ 物理回退完成: reset --hard {target} + clean -fd\n"
            f"  cwd: {cwd}"
        )
        return True

    def rollback_latest_change(self, task_id: str) -> Dict[str, Any]:
        safe_branch = f"{TASK_BRANCH_PREFIX}{task_id}"
        if not self._branch_exists(safe_branch):
            return {"success": False, "error": f"任务分支 {safe_branch} 不存在"}

        task_dir = self._verify_rollback_dir(task_id)
        if not task_dir:
            return {"success": False, "error": f"任务 {task_id} 的 worktree 不存在或无效"}

        log_result = self._run_git("log", "--oneline", "-5", cwd=task_dir)
        logger.info(f"📋 回退前最近 5 次提交 (cwd={task_dir}):\n{log_result.stdout}")

        status_before = self._run_git("status", "--short", cwd=task_dir)
        if status_before.stdout.strip():
            logger.info(f"📋 回退前未提交的变更:\n{status_before.stdout}")

        diff_info = self._capture_pre_rollback_diff("HEAD~1", task_dir)

        if self._hard_reset_with_clean("HEAD~1", task_dir):
            log_after = self._run_git("log", "--oneline", "-3", cwd=task_dir)
            logger.info(f"⏪ 任务 {task_id} 成功执行物理时光倒流\n{log_after.stdout}")
            return {
                "success": True,
                "task_id": task_id,
                "reverted_files": diff_info["file_list"],
                "changed_files_raw": diff_info["changed_files_raw"],
                "stat_summary": diff_info["stat_summary"],
                "detailed_diff": diff_info["detailed_diff"],
                "commits_being_reverted": diff_info["commits_being_reverted"],
                "untracked_files": diff_info["untracked_files"],
            }
        else:
            return {"success": False, "error": "git reset --hard HEAD~1 失败"}

    def rollback_task_step(self, task_id: str, steps: int = 1) -> Dict[str, Any]:
        safe_branch = f"{TASK_BRANCH_PREFIX}{task_id}"
        if not self._branch_exists(safe_branch):
            return {"success": False, "error": f"任务分支 {safe_branch} 不存在"}

        task_dir = self._verify_rollback_dir(task_id)
        if not task_dir:
            return {"success": False, "error": f"任务 {task_id} 的 worktree 不存在或无效"}

        log_result = self._run_git("log", "--oneline", f"-{steps + 2}", cwd=task_dir)
        logger.info(f"📋 回退前提交历史 (cwd={task_dir}):\n{log_result.stdout}")

        total_commits_result = self._run_git("rev-list", "--count", "HEAD", cwd=task_dir)
        try:
            total_commits = int(total_commits_result.stdout.strip())
        except ValueError:
            total_commits = 0

        if total_commits <= 1:
            return {"success": False, "error": "只有初始提交，无法再回退"}

        actual_steps = min(steps, total_commits - 1)

        diff_info = self._capture_pre_rollback_diff(f"HEAD~{actual_steps}", task_dir)

        if self._hard_reset_with_clean(f"HEAD~{actual_steps}", task_dir):
            log_after = self._run_git("log", "--oneline", "-5", cwd=task_dir)
            logger.info(f"⏪ 任务 {task_id} 回退了 {actual_steps} 步\n{log_after.stdout}")
            return {
                "success": True,
                "task_id": task_id,
                "steps_rolled_back": actual_steps,
                "remaining_commits": total_commits - actual_steps,
                "reverted_files": diff_info["file_list"],
                "changed_files_raw": diff_info["changed_files_raw"],
                "stat_summary": diff_info["stat_summary"],
                "detailed_diff": diff_info["detailed_diff"],
                "commits_being_reverted": diff_info["commits_being_reverted"],
                "untracked_files": diff_info["untracked_files"],
            }
        else:
            return {"success": False, "error": f"git reset --hard HEAD~{actual_steps} 失败"}

    def rollback_to_task_start(self, task_id: str) -> Dict[str, Any]:
        safe_branch = f"{TASK_BRANCH_PREFIX}{task_id}"
        if not self._branch_exists(safe_branch):
            return {"success": False, "error": f"任务分支 {safe_branch} 不存在"}

        task_dir = self._verify_rollback_dir(task_id)
        if not task_dir:
            return {"success": False, "error": f"任务 {task_id} 的 worktree 不存在或无效"}

        log_result = self._run_git("log", "--oneline", cwd=task_dir)
        lines = log_result.stdout.strip().split("\n")
        if len(lines) <= 1:
            return {"success": False, "error": "该任务分支只有初始提交，无法回退"}

        first_commit = lines[-1].split()[0]
        logger.info(f"📋 回退到任务起点: commit {first_commit} (cwd={task_dir})")

        diff_info = self._capture_pre_rollback_diff(first_commit, task_dir)

        if self._hard_reset_with_clean(first_commit, task_dir):
            logger.info(
                f"⏪ 任务 {task_id} 已回退到任务开始前状态 (commit {first_commit})"
            )
            return {
                "success": True,
                "task_id": task_id,
                "reverted_files": diff_info["file_list"],
                "changed_files_raw": diff_info["changed_files_raw"],
                "stat_summary": diff_info["stat_summary"],
                "detailed_diff": diff_info["detailed_diff"],
                "commits_being_reverted": diff_info["commits_being_reverted"],
                "untracked_files": diff_info["untracked_files"],
            }
        else:
            return {"success": False, "error": f"git reset --hard {first_commit} 失败"}

    def remove_task_workspace(self, task_id: str) -> bool:
        safe_branch = f"{TASK_BRANCH_PREFIX}{task_id}"
        task_dir = self._worktrees.get(task_id) or self._get_worktree_dir(task_id)

        if not _validate_path_not_protected(task_dir):
            logger.error(
                f"🚫 安全拦截: 拒绝删除受保护路径 {task_dir} "
                f"(BASE_REPO={self.workspace_dir}, WORKTREES_ROOT={self.worktree_base})"
            )
            return False

        if task_dir == self.workspace_dir:
            logger.error(f"🚫 安全拦截: 拒绝删除 BASE_REPO_DIR: {task_dir}")
            return False

        worktree_removed = False
        if os.path.exists(task_dir):
            worktree_removed = self._run_git_ok(
                "worktree", "remove", task_dir, "--force"
            )
            if not worktree_removed:
                import shutil
                try:
                    shutil.rmtree(task_dir, ignore_errors=True)
                    self._run_git_ok("worktree", "prune")
                    worktree_removed = True
                    logger.info(f"🗑️ 强制清理 worktree 目录: {task_dir}")
                except Exception as e:
                    logger.warning(f"强制清理 worktree 失败: {e}")

        if self._branch_exists(safe_branch):
            self._run_git_ok("branch", "-D", safe_branch)

        self._worktrees.pop(task_id, None)

        if worktree_removed or not os.path.exists(task_dir):
            logger.info(f"🗑️ 任务 {task_id} 的 worktree 和分支已彻底删除")
            return True
        else:
            logger.warning(f"⚠️ 任务 {task_id} 的 worktree 删除可能不完整")
            return False

    def abort_entire_task(self, task_id: str) -> bool:
        return self.remove_task_workspace(task_id)

    def get_task_commits(self, task_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        safe_branch = f"{TASK_BRANCH_PREFIX}{task_id}"
        if not self._branch_exists(safe_branch):
            return []

        task_dir = self._worktrees.get(task_id) or self._get_worktree_dir(task_id)
        if not os.path.exists(task_dir):
            return []

        result = self._run_git(
            "log", "--oneline", f"-{limit}", "--format=%H|%s|%ai", cwd=task_dir
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 2)
                if len(parts) >= 2:
                    commits.append(
                        {
                            "hash": parts[0][:8],
                            "message": parts[1] if len(parts) < 3 else parts[1],
                            "date": parts[2] if len(parts) >= 3 else "",
                        }
                    )
        return commits

    def get_status(self) -> Dict[str, Any]:
        branch = self._get_current_branch()
        status = self._run_git("status", "--porcelain")
        modified = (
            len(status.stdout.strip().split("\n")) if status.stdout.strip() else 0
        )
        with self._pool_lock:
            pool_size = len(self._warm_pool)
        return {
            "branch": branch,
            "modified_files": modified,
            "workspace_dir": self.workspace_dir,
            "active_worktrees": len(self._worktrees),
            "warm_pool_size": pool_size,
            "warm_pool_target": self._pool_size,
        }

    def get_warm_workspace(self) -> Optional[str]:
        with self._pool_lock:
            if self._warm_pool:
                entry = self._warm_pool.pop(0)
                warmup_dir = entry["warmup_dir"]
                warmup_branch = entry.get("warmup_branch", "")
                logger.info(
                    f"📦 预热沙盒借出: {os.path.basename(warmup_dir)} "
                    f"(池中剩余: {len(self._warm_pool)}/{self._pool_size})"
                )
                return warmup_dir

        logger.warning("📦 预热池为空，无法借出沙盒")
        return None

    def recycle_workspace(self, worktree_path: str) -> bool:
        if not worktree_path or not os.path.exists(worktree_path):
            logger.warning(f"♻️ 回收沙盒失败: 路径不存在 {worktree_path}")
            return False

        try:
            self._run_git_ok("checkout", ".", cwd=worktree_path)
            self._run_git_ok("clean", "-fd", cwd=worktree_path)

            warmup_id = os.path.basename(worktree_path).replace("warmup_", "")
            entry = {
                "warmup_id": warmup_id,
                "warmup_branch": f"{WARMUP_BRANCH_PREFIX}{warmup_id}",
                "warmup_dir": worktree_path,
            }

            with self._pool_lock:
                if len(self._warm_pool) < self._pool_size:
                    self._warm_pool.append(entry)
                    logger.info(
                        f"♻️ 沙盒已归还预热池: {os.path.basename(worktree_path)} "
                        f"(池中: {len(self._warm_pool)}/{self._pool_size})"
                    )
                else:
                    logger.info(f"♻️ 预热池已满，销毁沙盒: {os.path.basename(worktree_path)}")
                    self._run_git_ok("worktree", "remove", worktree_path, "--force")
                    branch_name = f"{WARMUP_BRANCH_PREFIX}{warmup_id}"
                    if self._branch_exists(branch_name):
                        self._run_git_ok("branch", "-D", branch_name)

            return True
        except Exception as e:
            logger.error(f"♻️ 回收沙盒异常: {e}")
            return False

    def merge_task_to_main(self, task_id: str, force: bool = False) -> Dict[str, Any]:
        safe_branch = f"{TASK_BRANCH_PREFIX}{task_id}"

        if not self._branch_exists(safe_branch):
            return {"status": "error", "message": f"任务分支 {safe_branch} 不存在"}

        task_dir = self._worktrees.get(task_id) or self._get_worktree_dir(task_id)
        if not os.path.exists(task_dir):
            return {"status": "error", "message": f"任务 {task_id} 的 worktree 不存在"}

        log_result = self._run_git("log", "--oneline", cwd=task_dir)
        if not log_result.stdout.strip():
            return {"status": "error", "message": f"任务 {task_id} 没有任何提交，无法合并"}

        self._run_git("add", ".", cwd=self.workspace_dir)
        status = self._run_git("status", "--porcelain", cwd=self.workspace_dir)
        if status.stdout.strip():
            self._run_git(
                "commit",
                "-m",
                "Auto-save before merge",
                cwd=self.workspace_dir,
            )

        main_branch = self._get_current_branch()
        self._run_git("checkout", main_branch, cwd=self.workspace_dir)

        if force:
            result = self._run_git(
                "merge", safe_branch, "-X", "theirs", "-m",
                f"Merge task {task_id} (force: accept task changes)",
                cwd=self.workspace_dir,
            )
        else:
            result = self._run_git("merge", safe_branch, cwd=self.workspace_dir)

        if result.returncode == 0:
            head_result = self._run_git("rev-parse", "HEAD", cwd=self.workspace_dir)
            merge_commit_hash = head_result.stdout.strip()[:12] if head_result.returncode == 0 else ""

            logger.info(f"✅ 任务 {task_id} 完美合入主干 {main_branch}！merge_commit={merge_commit_hash}")

            task_dir = self._worktrees.get(task_id) or self._get_worktree_dir(task_id)
            if task_dir and os.path.exists(task_dir):
                self._run_git_ok("worktree", "remove", task_dir, "--force")
                logger.info(f"🗑️ 已清理任务 {task_id} 的 worktree: {task_dir}")
            if self._branch_exists(safe_branch):
                self._run_git_ok("branch", "-d", safe_branch)
                logger.info(f"🗑️ 已删除任务分支: {safe_branch}")
            self._worktrees.pop(task_id, None)
            self._run_git_ok("worktree", "prune")

            return {
                "status": "success",
                "message": f"任务「{task_id}」已成功合入主干",
                "task_id": task_id,
                "main_branch": main_branch,
                "merge_commit_hash": merge_commit_hash,
            }
        else:
            if force:
                self._run_git("merge", "--abort", cwd=self.workspace_dir)
                logger.error(f"❌ 强制合并也失败了: {result.stderr[:200]}")
                return {
                    "status": "error",
                    "message": f"强制合并失败: {result.stderr[:200]}",
                    "task_id": task_id,
                }

            conflict_files = self._run_git(
                "diff", "--name-only", "--diff-filter=U", cwd=self.workspace_dir
            )
            conflict_list = conflict_files.stdout.strip().split("\n") if conflict_files.stdout.strip() else []

            conflict_detail = self._run_git(
                "diff", "--name-only", safe_branch, cwd=self.workspace_dir
            )
            if not conflict_list and conflict_detail.stdout.strip():
                conflict_list = conflict_detail.stdout.strip().split("\n")

            self._run_git("merge", "--abort", cwd=self.workspace_dir)
            logger.warning(f"⚠️ 任务 {task_id} 与主干发生冲突，已撤销合并操作。冲突文件: {conflict_list}")

            return {
                "status": "conflict",
                "message": f"文件存在冲突（{len(conflict_list)} 个文件），可以选择强制合并（以任务分支为准）或放弃合并",
                "task_id": task_id,
                "conflict_files": conflict_list,
                "details": result.stdout + result.stderr,
            }

    def revert_merged_task(self, task_id: str, merge_commit_hash: str = "") -> Dict[str, Any]:
        if not merge_commit_hash:
            return {"status": "error", "message": "未提供合并提交的 hash，无法执行 revert"}

        main_branch = self._get_current_branch()
        self._run_git("checkout", main_branch, cwd=self.workspace_dir)

        result = self._run_git("revert", "-m", "1", merge_commit_hash, "--no-edit", cwd=self.workspace_dir)

        if result.returncode == 0:
            logger.info(f"🚑 主干已生成反向补丁，任务 {task_id} 的影响已被安全抵消")
            return {
                "status": "success",
                "message": f"任务「{task_id}」的影响已通过 revert 安全抵消",
                "task_id": task_id,
            }
        else:
            self._run_git("revert", "--abort", cwd=self.workspace_dir)
            logger.warning(f"⚠️ revert 操作失败: {result.stderr}")
            return {
                "status": "error",
                "message": f"revert 失败: {result.stderr[:200]}",
                "task_id": task_id,
            }

    def shutdown(self):
        self._pool_maintainer_stop.set()
        with self._pool_lock:
            for entry in self._warm_pool:
                warmup_dir = entry["warmup_dir"]
                warmup_branch = entry["warmup_branch"]
                if os.path.exists(warmup_dir):
                    self._run_git_ok("worktree", "remove", warmup_dir, "--force")
                if self._branch_exists(warmup_branch):
                    self._run_git_ok("branch", "-D", warmup_branch)
            self._warm_pool.clear()
        logger.info("🏊 WarmPool 预热池已关闭并清理")


_sandboxes: Dict[str, GitSandboxManager] = {}

_global_sandbox: Optional[GitSandboxManager] = None
_global_lock = threading.Lock()


def init_global_sandbox(
    base_repo_dir: Optional[str] = None,
    worktrees_root: Optional[str] = None,
    pool_size: int = 3,
) -> GitSandboxManager:
    global _global_sandbox
    with _global_lock:
        if _global_sandbox is None:
            _global_sandbox = GitSandboxManager(
                base_repo_dir=base_repo_dir,
                worktrees_root=worktrees_root,
                pool_size=pool_size,
            )
            logger.info("🌍 全局 GitSandboxManager 已初始化 (单例)")
        return _global_sandbox


def get_global_sandbox() -> Optional[GitSandboxManager]:
    return _global_sandbox


def get_sandbox(workspace_dir: str = "", pool_size: int = 3) -> GitSandboxManager:
    if _global_sandbox is not None:
        return _global_sandbox

    abs_dir = os.path.abspath(workspace_dir or BASE_REPO_DIR)
    if abs_dir not in _sandboxes:
        _sandboxes[abs_dir] = GitSandboxManager(
            base_repo_dir=abs_dir,
            pool_size=pool_size,
        )
    return _sandboxes[abs_dir]
