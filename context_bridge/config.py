"""Configuration for project mapping via CLAUDE.md tags."""

import json
import os
import re
import time

CACHE_FILE = ".claude-project-cache"
DEFAULT_COOLDOWN = 120  # 2 minutes


class ProjectConfig:
    """Reads project mapping from CLAUDE.md and manages local cache."""

    def __init__(self, cwd: str = None, cooldown_seconds: int = DEFAULT_COOLDOWN):
        self.cwd = cwd or os.getcwd()
        self.cooldown_seconds = cooldown_seconds
        self._project_name = None
        self._project_id = None
        self._parsed = False

    def _parse_claude_md(self):
        if self._parsed:
            return
        self._parsed = True
        claude_md_path = os.path.join(self.cwd, "CLAUDE.md")
        if not os.path.exists(claude_md_path):
            return
        with open(claude_md_path, "r") as f:
            content = f.read()
        id_match = re.search(r"<!--\s*claude-project-id:\s*(.+?)\s*-->", content)
        if id_match:
            self._project_id = id_match.group(1).strip()
        name_match = re.search(r"<!--\s*claude-project:\s*(.+?)\s*-->", content)
        if name_match:
            self._project_name = name_match.group(1).strip()

    @property
    def project_name(self) -> str | None:
        self._parse_claude_md()
        return self._project_name

    @property
    def project_id(self) -> str | None:
        self._parse_claude_md()
        return self._project_id

    @property
    def repo_name(self) -> str:
        return os.path.basename(self.cwd)

    def _read_cache(self) -> dict:
        cache_path = os.path.join(self.cwd, CACHE_FILE)
        if not os.path.exists(cache_path):
            return {}
        try:
            with open(cache_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}

    @property
    def cached_project_id(self) -> str | None:
        return self._read_cache().get("project_id")

    def _write_cache(self, updates: dict) -> None:
        cache_path = os.path.join(self.cwd, CACHE_FILE)
        data = self._read_cache()
        data.update(updates)
        with open(cache_path, "w") as f:
            json.dump(data, f, indent=2)

    def save_cached_project_id(self, project_id: str) -> None:
        self._write_cache({"project_id": project_id})

    def is_push_allowed(self) -> bool:
        last_push = self._read_cache().get("last_push_time")
        if last_push is None:
            return True
        return (time.time() - last_push) >= self.cooldown_seconds

    def record_push(self) -> None:
        self._write_cache({"last_push_time": time.time()})
