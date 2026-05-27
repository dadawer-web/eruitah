import os
import logging

logger = logging.getLogger(__name__)

WORKTREES_ROOT = os.environ.get(
    "ERUITAH_WORKTREES_ROOT",
    os.path.join(os.path.expanduser("~"), "agent-worktrees"),
)

USER_DATA_ROOT = os.environ.get(
    "ERUITAH_USER_DATA_ROOT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".user_data"),
)

PROTECTED_PREFIXES = [
    "/etc",
    "/root",
    "/boot",
    "/dev",
    "/proc",
    "/sys",
    "/lib",
]

ALLOWED_OUTSIDE_PREFIXES = [
    "/tmp",
    "/dev/null",
    "/dev/zero",
    "/dev/urandom",
    "/dev/stdin",
    "/dev/stdout",
    "/dev/stderr",
    "/proc/self/fd",
    "/usr",
    "/bin",
    "/sbin",
    "/opt",
    "/var",
]

READONLY_SYSTEM_PREFIXES = [
    "/usr",
    "/bin",
    "/sbin",
    "/opt",
    "/var",
]


def get_user_work_dir(user_id: int, session_id: str) -> str:
    return os.path.join(WORKTREES_ROOT, f"user_{user_id}", session_id)


def get_user_task_dir(user_id: int) -> str:
    d = os.path.join(USER_DATA_ROOT, f"user_{user_id}", "tasks")
    os.makedirs(d, exist_ok=True)
    return d


def get_user_snapshot_dir(user_id: int) -> str:
    d = os.path.join(USER_DATA_ROOT, f"user_{user_id}", "checkpoints")
    os.makedirs(d, exist_ok=True)
    return d


def get_user_checkpoint_dir(user_id: int, session_id: str) -> str:
    d = os.path.join(USER_DATA_ROOT, f"user_{user_id}", "checkpoints", session_id)
    os.makedirs(d, exist_ok=True)
    return d


def get_user_checkpoint_db(user_id: int, session_id: str) -> str:
    d = get_user_checkpoint_dir(user_id, session_id)
    return os.path.join(d, "rewind.db")


def get_user_task_filepath(user_id: int, task_id: str) -> str:
    d = get_user_task_dir(user_id)
    return os.path.join(d, f"{task_id}.json")


def get_user_snapshot_path(user_id: int, task_id: str) -> str:
    d = get_user_snapshot_dir(user_id)
    return os.path.join(d, f"{task_id}_pre")


def validate_path_in_sandbox(file_path: str, sandbox_dir: str) -> tuple[bool, str]:
    if not file_path:
        return False, "empty path"

    abs_path = os.path.abspath(os.path.expanduser(file_path))
    abs_sandbox = os.path.abspath(sandbox_dir)

    if abs_path.startswith(abs_sandbox + os.sep) or abs_path == abs_sandbox:
        return True, ""

    for prefix in ALLOWED_OUTSIDE_PREFIXES:
        if abs_path.startswith(prefix + os.sep) or abs_path == prefix:
            return True, ""

    if abs_path.startswith(WORKTREES_ROOT + os.sep) or abs_path == WORKTREES_ROOT:
        return True, ""

    user_home = os.path.expanduser("~")
    if abs_path == user_home or abs_path.startswith(user_home + os.sep):
        if not abs_path.startswith("/root"):
            return True, ""

    for prefix in PROTECTED_PREFIXES:
        if abs_path.startswith(prefix + os.sep) or abs_path == prefix:
            if not abs_sandbox.startswith(prefix):
                return False, f"path '{file_path}' is in protected system directory '{prefix}'"

    if not abs_path.startswith(abs_sandbox):
        return False, f"path '{file_path}' is outside sandbox '{sandbox_dir}'"

    return True, ""


def enforce_sandbox_path(file_path: str, sandbox_dir: str) -> str:
    ok, reason = validate_path_in_sandbox(file_path, sandbox_dir)
    if not ok:
        raise PermissionError(f"Sandbox violation: {reason}")
    return os.path.abspath(os.path.expanduser(file_path))
