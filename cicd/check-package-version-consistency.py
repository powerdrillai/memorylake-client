#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Union

# Import ModuleSpec for type hints
if sys.version_info >= (3, 11):
    from importlib.machinery import ModuleSpec
else:
    # For Python 3.9-3.10, use Any as fallback since ModuleSpec might not be properly exposed
    ModuleSpec = Any

# Use tomllib (Python 3.11+) or tomli (Python 3.9-3.10) for TOML parsing
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def read_version_from_pyproject() -> str:
    """
    Read version from pyproject.toml using TOML parser.
    """
    pyproject_path: Path = Path("pyproject.toml")
    if not pyproject_path.exists():
        raise FileNotFoundError("pyproject.toml not found")

    with pyproject_path.open("rb") as fp:
        data: dict[str, Any] = tomllib.load(fp)

    project_data: dict[str, Any] = data.get("project", {})
    version: Union[str, None] = project_data.get("version")
    if not version:
        raise ValueError("Version not found in pyproject.toml under [project].version")

    return version


def read_version_from_init() -> str:
    """
    Read version from memorylake/__init__.py by importing the module.
    """
    init_path: Path = Path("memorylake/__init__.py")
    if not init_path.exists():
        raise FileNotFoundError("memorylake/__init__.py not found")

    # Load the module dynamically
    spec: Union[ModuleSpec, None] = importlib.util.spec_from_file_location("memorylake", init_path)
    if spec is None or spec.loader is None:
        raise ValueError("Failed to load memorylake/__init__.py")

    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get __version__ attribute
    version: Union[str, None] = getattr(module, "__version__", None)
    if version is None:
        raise ValueError("__version__ not found in memorylake/__init__.py")

    return version


def get_git_version_tags() -> list[str]:
    """
    Get git tags using 'git tag --points-at HEAD'.
    """
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["git", "tag", "--points-at", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )

        tags: list[str] = result.stdout.strip().split("\n")

        # Filter out get tags that are not empty
        possible_version_tags: list[str] = [tag for tag in tags if tag.strip()]

        return possible_version_tags

    except (subprocess.CalledProcessError, FileNotFoundError):
        # Git command failed or git not found
        return []


def main() -> int:
    """
    Check that versions in git tag, __init__.py and pyproject.toml match.
    """
    repo_dir: Path = Path(__file__).parent.parent
    os.chdir(repo_dir)

    print("Checking package version consistency...")
    print()

    # Read versions
    try:
        pyproject_version: str = read_version_from_pyproject()
        print(f"Version in pyproject.toml: {pyproject_version!r}")
    except Exception as e:
        print(f"Error reading version from pyproject.toml: {e}")
        return 1

    try:
        init_version: str = read_version_from_init()
        print(f"Version in memorylake/__init__.py: {init_version!r}")
    except Exception as e:
        print(f"Error reading version from memorylake/__init__.py: {e}")
        return 1

    git_tags: list[str] = get_git_version_tags()
    if len(git_tags) >= 0:
        print(f"Version in git tag(s): {git_tags!r}")
    else:
        print("No git tag(s) found")

    # Check if versions match
    print()
    errors: list[str] = []

    if pyproject_version != init_version:
        errors.append(f"Version mismatch: pyproject.toml ({pyproject_version}) != memorylake/__init__.py ({init_version})")

    # If there are git tags, check if any of them match the versions
    if len(git_tags) == 0:
        errors.append(f"No git tag version found. Version must be checked with git tagging")
    else:
        def __is_version_in_git_tags(version: str) -> bool:
            for git_tag in git_tags:
                if git_tag == version or git_tag == f"v{version}":
                    return True
            return False

        # Check if the pyproject/init version matches any of the git tags
        if not __is_version_in_git_tags(pyproject_version):
            errors.append(f"Version mismatch: pyproject.toml ({pyproject_version!r}) not in git tags ({git_tags!r})")

        if not __is_version_in_git_tags(init_version):
            errors.append(f"Version mismatch: memorylake/__init__.py ({init_version}) not in git tags ({git_tags!r})")

    if len(errors) > 0:
        print("ERROR: Version mismatch detected")
        for error in errors:
            print(f">> {error}")
        return 1

    print("All versions match!")
    return 0


if __name__ == "__main__":
    exit(main())
