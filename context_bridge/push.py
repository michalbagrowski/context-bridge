# context_bridge/push.py
"""CLI entry point for auto-pushing context to claude.ai Projects."""

import argparse
import sys

from context_bridge.config import ProjectConfig
from context_bridge.content_generator import ContentGenerator
from context_bridge.projects_api import ProjectsAPI


def auto_push():
    """Auto-push status summary to the configured project."""
    config = ProjectConfig()

    if not config.is_push_allowed():
        print("Skipping push: cooldown active", file=sys.stderr)
        return

    api = ProjectsAPI()

    project_id = config.project_id or config.cached_project_id
    if not project_id and config.project_name:
        project_id = api.resolve_project_id(config.project_name)
        if project_id:
            config.save_cached_project_id(project_id)

    if not project_id:
        print("No project configured. Add <!-- claude-project: Name --> to CLAUDE.md", file=sys.stderr)
        sys.exit(1)
    gen = ContentGenerator(repo_name=config.repo_name)

    # Push status summary
    content = gen.generate_status()
    doc_name = gen.status_doc_name()
    result = api.upsert_doc(project_id, doc_name, content)
    print(f"Pushed: {doc_name} (id: {result.get('uuid')})")

    config.record_push()


def main():
    parser = argparse.ArgumentParser(description="Context Bridge push CLI")
    parser.add_argument("--auto", action="store_true", help="Auto-push status summary")
    args = parser.parse_args()

    if args.auto:
        auto_push()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
