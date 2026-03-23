"""Generate structured markdown documents for pushing to claude.ai Projects."""

import subprocess
from datetime import datetime


class ContentGenerator:
    """Generates status summaries, TODO lists, and session logs from git state."""

    def __init__(self, repo_name: str, cwd: str = None):
        self.repo_name = repo_name
        self.cwd = cwd

    def _git(self, *args: str) -> str:
        """Run a git command and return stripped stdout."""
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True,
            text=True,
            cwd=self.cwd,
        )
        return result.stdout.strip()

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def status_doc_name(self) -> str:
        return f"[cli] Status - {self.repo_name}.md"

    def todos_doc_name(self) -> str:
        return f"[cli] TODOs - {self.repo_name}.md"

    def session_log_doc_name(self) -> str:
        return f"[cli] Session Log - {self.repo_name} - {self._today()}.md"

    def generate_status(self) -> str:
        """Generate a status summary from git state."""
        branch = self._git("branch", "--show-current")
        log = self._git("log", "--oneline", "-10", "--no-decorate")
        # Try common default branch names; empty string if no remote
        ahead = ""
        for default in ["origin/main", "origin/master"]:
            ahead = self._git("rev-list", "--count", f"{default}..HEAD")
            if ahead:
                break

        lines = [
            f"# CLI Status: {self.repo_name}",
            f"Last updated: {self._now()}",
            "",
            "## Recent Changes",
        ]
        for entry in log.splitlines():
            if entry:
                lines.append(f"- {entry}")

        lines.extend([
            "",
            "## Current Branch",
            f"{branch} ({ahead} commits ahead of main)"
            if ahead and ahead != "0"
            else branch,
        ])

        return "\n".join(lines) + "\n"

    def generate_todos(self, todos: list[str]) -> str:
        """Generate a TODO list document."""
        lines = [
            f"# TODOs: {self.repo_name}",
            f"Last updated: {self._now()}",
            "",
        ]
        for todo in todos:
            if todo.startswith("[x]") or todo.startswith("[X]"):
                lines.append(f"- [{todo[1]}] {todo[3:].strip()}")
            else:
                lines.append(f"- [ ] {todo}")

        return "\n".join(lines) + "\n"

    def generate_session_log(
        self,
        done: list[str],
        decisions: list[str] = None,
        needs_work: list[str] = None,
    ) -> str:
        """Generate a session log entry."""
        lines = [
            f"# Session Log: {self.repo_name}",
            f"Date: {self._today()}",
            "",
            "## What was done",
        ]
        for item in done:
            lines.append(f"- {item}")

        if decisions:
            lines.extend(["", "## Decisions made"])
            for item in decisions:
                lines.append(f"- {item}")

        if needs_work:
            lines.extend(["", "## What needs work"])
            for item in needs_work:
                lines.append(f"- {item}")

        return "\n".join(lines) + "\n"
