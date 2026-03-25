"""Projects API — list projects, CRUD knowledge docs, list project conversations."""

import json

from context_bridge.auth import ClaudeAuth


class ProjectsAPI:
    """Interacts with claude.ai Projects via internal API."""

    def __init__(self, auth: ClaudeAuth = None):
        self._auth = auth or ClaudeAuth()

    def _org_id(self) -> str:
        return self._auth.get_organization_id()

    def list_projects(self) -> str:
        """List all projects in the organization."""
        try:
            projects = self._auth.get(f"organizations/{self._org_id()}/projects")
            result = [
                {
                    "id": p.get("uuid"),
                    "name": p.get("name"),
                    "description": p.get("description", ""),
                }
                for p in projects
            ]
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def list_project_docs(self, project_id: str) -> str:
        """List all knowledge docs in a project."""
        try:
            docs = self._auth.get(
                f"organizations/{self._org_id()}/projects/{project_id}/docs"
            )
            result = [
                {
                    "id": d.get("uuid"),
                    "file_name": d.get("file_name"),
                    "created_at": d.get("created_at"),
                }
                for d in docs
            ]
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_project_doc(self, project_id: str, doc_id: str) -> str:
        """Get content of a specific knowledge doc."""
        try:
            docs = self._auth.get(
                f"organizations/{self._org_id()}/projects/{project_id}/docs"
            )
            for doc in docs:
                if doc.get("uuid") == doc_id:
                    return json.dumps({
                        "id": doc.get("uuid"),
                        "file_name": doc.get("file_name"),
                        "content": doc.get("content", ""),
                        "created_at": doc.get("created_at"),
                    }, indent=2)
            return json.dumps({"error": f"Doc {doc_id} not found"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def list_project_conversations(self, project_id: str) -> str:
        """List conversations within a project."""
        try:
            conversations = self._auth.get(
                f"organizations/{self._org_id()}/projects/{project_id}/chat_conversations"
            )
            result = [
                {
                    "id": c.get("uuid"),
                    "name": c.get("name") or "Untitled",
                    "created_at": c.get("created_at"),
                    "updated_at": c.get("updated_at"),
                }
                for c in conversations
            ]
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def create_doc(self, project_id: str, file_name: str, content: str) -> dict:
        """Create a knowledge doc in a project. Returns raw API response."""
        return self._auth.post(
            f"organizations/{self._org_id()}/projects/{project_id}/docs",
            {"file_name": file_name, "content": content},
        )

    def delete_doc(self, project_id: str, doc_id: str) -> None:
        """Delete a knowledge doc from a project."""
        self._auth.delete(
            f"organizations/{self._org_id()}/projects/{project_id}/docs/{doc_id}"
        )

    def upsert_doc(self, project_id: str, file_name: str, content: str) -> dict:
        """Create or replace a doc by file_name. Deletes existing if found."""
        docs = self._auth.get(
            f"organizations/{self._org_id()}/projects/{project_id}/docs"
        )
        for doc in docs:
            if doc.get("file_name") == file_name:
                self.delete_doc(project_id, doc["uuid"])
                break
        return self.create_doc(project_id, file_name, content)

    def resolve_project_id(self, project_name: str) -> str | None:
        """Find a project UUID by name (case-insensitive). Returns None if not found."""
        projects = self._auth.get(f"organizations/{self._org_id()}/projects")
        name_lower = project_name.lower()
        for project in projects:
            if project.get("name", "").lower() == name_lower:
                return project["uuid"]
        return None
