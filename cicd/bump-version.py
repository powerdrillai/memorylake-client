#!/usr/bin/env python3

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional


def validate_version(version: str) -> bool:
    """
    Validate that the version string follows basic semver format (X.Y.Z).
    """
    pattern: str = r"^\d+\.\d+\.\d+$"
    return bool(re.match(pattern, version))


def update_pyproject_version(new_version: str) -> None:
    """
    Update version in pyproject.toml.
    """
    pyproject_path: Path = Path("pyproject.toml")
    if not pyproject_path.exists():
        raise FileNotFoundError("pyproject.toml not found")

    content: str = pyproject_path.read_text()

    # Use regex to replace the version line under [project]
    pattern: str = r'^(version\s*=\s*")[^"]+(")'
    match: Optional[re.Match[str]] = re.search(pattern, content, flags=re.MULTILINE)
    
    if not match:
        raise ValueError("Could not find version field in pyproject.toml")

    new_content: str = re.sub(pattern, rf"\g<1>{new_version}\g<2>", content, flags=re.MULTILINE)
    pyproject_path.write_text(new_content)
    print(f"Updated pyproject.toml: version = \"{new_version}\"")


def update_init_version(new_version: str) -> None:
    """
    Update version in memorylake/__init__.py.
    """
    init_path: Path = Path("memorylake/__init__.py")
    if not init_path.exists():
        raise FileNotFoundError("memorylake/__init__.py not found")

    content: str = init_path.read_text()

    # Use regex to replace the __version__ line
    pattern: str = r'^(__version__\s*:\s*str\s*=\s*")[^"]+(")$'
    match: Optional[re.Match[str]] = re.search(pattern, content, flags=re.MULTILINE)
    
    if not match:
        raise ValueError("Could not find __version__ field in memorylake/__init__.py")

    new_content: str = re.sub(pattern, rf"\g<1>{new_version}\g<2>", content, flags=re.MULTILINE)
    init_path.write_text(new_content)
    print(f"Updated memorylake/__init__.py: __version__ = \"{new_version}\"")


def main() -> int:
    """
    Bump version in pyproject.toml and memorylake/__init__.py.
    """
    if len(sys.argv) != 2:
        print("Usage: bump-version.py <version>")
        print("Example: bump-version.py 1.2.3")
        return 1

    new_version: str = sys.argv[1]

    # Validate version format
    if not validate_version(new_version):
        print(f"ERROR: Invalid version format: {new_version!r}")
        print("Version must follow semver format (e.g., 0.1.1, 1.0.0)")
        return 1

    # Change to repository root
    repo_dir: Path = Path(__file__).parent.parent
    os.chdir(repo_dir)

    print(f"Bumping version to {new_version!r}...")
    print()

    # Update files
    try:
        update_pyproject_version(new_version)
        update_init_version(new_version)
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    print()
    print(f"Successfully bumped version to {new_version!r}")
    return 0


if __name__ == "__main__":
    exit(main())
