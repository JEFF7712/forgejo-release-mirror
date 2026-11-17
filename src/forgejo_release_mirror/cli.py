from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
from importlib.metadata import version

from .mirror import API, synchronize


def token(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or any(character.isspace() for character in value):
        raise ValueError(f"{name} must contain a nonempty token without whitespace")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mirror published Forgejo releases and verified assets to GitHub"
    )
    parser.add_argument(
        "--forgejo-origin", required=True, help="Forgejo scheme and host"
    )
    parser.add_argument("--source-repository", required=True, metavar="OWNER/REPO")
    parser.add_argument(
        "--destination-repository",
        metavar="OWNER/REPO",
        help="GitHub repository (defaults to the source repository name)",
    )
    parser.add_argument(
        "--minimum-version", required=True, help="Oldest version tag to manage"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check tag parity and list releases and assets without changing GitHub",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('forgejo-release-mirror')}",
    )
    args = parser.parse_args(argv)
    try:
        forgejo = API(args.forgejo_origin, token("FORGEJO_READ_TOKEN"), "/api/v1")
        github = API("https://api.github.com", token("GITHUB_TOKEN"))
        results = synchronize(
            forgejo,
            github,
            args.source_repository,
            args.minimum_version,
            destination_repository=args.destination_repository,
            dry_run=args.dry_run,
        )
    except (
        RuntimeError,
        ValueError,
        OSError,
        KeyError,
        http.client.HTTPException,
    ) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", "dry_run": args.dry_run, "releases": results}))
    return 0
