"""Clone or update library repos and install project dependencies."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

LIBS_DIR = Path(__file__).parent / "libs"

REPOS = [
    {
        "name": "locale",
        "url": "https://github.com/thunderbird/thunderbird.net-l10n.git",
        "dest": LIBS_DIR / "locale",
    },
    {
        "name": "product-details",
        "url": "https://github.com/mozilla-releng/product-details.git",
        "branch": "production",
        "dest": LIBS_DIR / "product-details",
    },
    {
        "name": "thunderbird-notes",
        "url": "https://github.com/thunderbird/thunderbird-notes.git",
        "dest": LIBS_DIR / "thunderbird_notes",
    },
    {
        "name": "roadmaps",
        "url": "https://github.com/thunderbird/roadmaps-overview.git",
        "dest": LIBS_DIR / "thunderbird_roadmaps",
    },
]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def sync_repo(repo: dict) -> None:
    dest = repo["dest"]
    branch = repo.get("branch")

    if dest.exists():
        print(f"Updating {repo['name']}...")
        try:
            run(["git", "pull"], cwd=dest)
        except subprocess.CalledProcessError:
            print(f"  WARNING: git pull failed for {repo['name']}, skipping.")
    else:
        print(f"Cloning {repo['name']}...")
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["-b", branch]
        cmd += [repo["url"], str(dest)]
        run(cmd)


def install_python_deps() -> None:
    print("Installing Python dependencies...")
    run(["uv", "sync"])


def install_less() -> None:
    if shutil.which("lessc"):
        print("less is already installed.")
        return

    if not shutil.which("npm"):
        print("ERROR: npm is not installed. Install Node.js/npm first.", file=sys.stderr)
        sys.exit(1)

    print("Installing less...")
    run(["npm", "install", "-g", "less"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-sync", action="store_true",
        help="Skip uv sync (use when dependencies are already installed)",
    )
    parser.add_argument(
        "--notes-branch", default=None,
        help="Branch to use for thunderbird-notes (default: repo default)",
    )
    args = parser.parse_args()

    if not args.skip_sync:
        install_python_deps()

    LIBS_DIR.mkdir(exist_ok=True)
    for repo in REPOS:
        if args.notes_branch and repo["name"] == "thunderbird-notes":
            repo = {**repo, "branch": args.notes_branch}
        sync_repo(repo)

    install_less()

    print("\nSetup complete. Run 'uv run build-site.py' to build the site.")


if __name__ == "__main__":
    main()
