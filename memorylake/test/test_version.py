import importlib
import sys
from pathlib import Path
from typing import Any, cast

if sys.version_info >= (3, 11):
    import tomllib as _tomllib  # type: ignore[import-not-found]
else:
    _tomllib = importlib.import_module("tomli")

tomllib: Any = _tomllib


def test_version_number_match() -> None:
    import memorylake
    assert hasattr(memorylake, "__version__")

    # Try to read version from pyproject.toml, and check they are the same

    # Get the directory of the current file
    current_dir: Path = Path(__file__).parent
    project_root: Path = current_dir.parent.parent
    pyproject_path: Path = project_root / "pyproject.toml"

    # Read the version from pyproject.toml
    with pyproject_path.open("rb") as fp:
        loaded_data: Any = tomllib.load(fp)

    if not isinstance(loaded_data, dict):
        raise AssertionError("pyproject.toml must load to a dictionary")

    project_map = cast(dict[str, Any], loaded_data)
    project_section_obj = project_map.get("project")
    if not isinstance(project_section_obj, dict):
        raise AssertionError("pyproject.toml must contain a project table")

    project_section = cast(dict[str, Any], project_section_obj)
    version_obj = project_section.get("version")
    if not isinstance(version_obj, str):
        raise AssertionError("project.version must be a string")

    pyproject_version = version_obj

    # Check that the versions match
    assert memorylake.__version__ == pyproject_version
