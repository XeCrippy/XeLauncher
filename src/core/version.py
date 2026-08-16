from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGED_VERSION = "0.2.0"


def _pyproject_version() -> str:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        lines = pyproject.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    in_project = False
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if in_project and line.startswith("version") and "=" in line:
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                return value[1:-1]
    return ""


def app_version() -> str:
    source_version = _pyproject_version()
    if source_version:
        return source_version

    try:
        return version("XeLauncher")
    except PackageNotFoundError:
        return PACKAGED_VERSION


APP_VERSION = app_version()
