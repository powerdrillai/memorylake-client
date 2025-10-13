import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


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
        pyproject_data: dict[str, Any] = tomllib.load(fp)
        pyproject_version: str = pyproject_data["project"]["version"]

    # Check that the versions match
    assert memorylake.__version__ == pyproject_version
