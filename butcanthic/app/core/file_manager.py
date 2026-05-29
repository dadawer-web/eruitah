"""
文件管理器 - 统一管理上传文件和处理结果
所有文件存放在 temp_workspace/ 下，按类型隔离
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class FileManager:

    def __init__(self, workspace_root: str = "temp_workspace"):
        self.workspace_root = workspace_root
        self._base_upload_dir = os.path.join(workspace_root, "uploads")
        self._base_output_dir = os.path.join(workspace_root, "output")

    def _get_user_upload_dir(self, user_id: Optional[str] = None) -> str:
        if user_id:
            return os.path.join(self._base_upload_dir, f"user_{user_id}")
        return self._base_upload_dir

    def _get_user_output_dir(self, user_id: Optional[str] = None) -> str:
        if user_id:
            return os.path.join(self._base_output_dir, f"user_{user_id}")
        return self._base_output_dir

    def init_workspace(self):
        for subdir in ["word", "excel", "ppt"]:
            os.makedirs(os.path.join(self._base_upload_dir, subdir), exist_ok=True)
        os.makedirs(self._base_output_dir, exist_ok=True)
        logger.info(f"Workspace initialized: {self.workspace_root}")

    def save_upload(
        self,
        filename: str,
        content: bytes,
        file_type: str = "word",
        user_id: Optional[str] = None,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        subdir = {"docx": "word", "xlsx": "excel", "csv": "excel", "pptx": "ppt"}.get(file_type, "word")
        base = self._get_user_upload_dir(user_id)
        dest_dir = os.path.join(base, subdir)
        os.makedirs(dest_dir, exist_ok=True)
        file_path = os.path.join(dest_dir, f"{task_id}_{filename}")
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"File saved: {file_path} (user={user_id or 'anonymous'})")
        return file_path

    def save_output(self, filename: str, content: bytes, user_id: Optional[str] = None) -> str:
        out_dir = self._get_user_output_dir(user_id)
        os.makedirs(out_dir, exist_ok=True)
        file_path = os.path.join(out_dir, filename)
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"Output saved: {file_path} (user={user_id or 'anonymous'})")
        return file_path

    def get_output_path(self, filename: str, user_id: Optional[str] = None) -> Optional[str]:
        out_dir = self._get_user_output_dir(user_id)
        file_path = os.path.join(out_dir, filename)
        if os.path.exists(file_path):
            return file_path
        if user_id:
            fallback = os.path.join(self._base_output_dir, filename)
            if os.path.exists(fallback):
                return fallback
        return None

    def get_upload_path(self, filename: str, user_id: Optional[str] = None) -> Optional[str]:
        base = self._get_user_upload_dir(user_id)
        for subdir in ["word", "excel", "ppt"]:
            file_path = os.path.join(base, subdir, filename)
            if os.path.exists(file_path):
                return file_path
        if user_id:
            for subdir in ["word", "excel", "ppt"]:
                file_path = os.path.join(self._base_upload_dir, subdir, filename)
                if os.path.exists(file_path):
                    return file_path
        return None

    def generate_output_filename(self, original_name: str, suffix: str = "智能填充") -> str:
        stem = os.path.splitext(original_name)[0]
        ext = os.path.splitext(original_name)[1]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{stem}_{suffix}_{timestamp}{ext}"

    def cleanup_old_files(self, max_age_hours: int = 24):
        import time

        cutoff = time.time() - max_age_hours * 3600
        for root, dirs, files in os.walk(self.workspace_root):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass


file_manager = FileManager()
