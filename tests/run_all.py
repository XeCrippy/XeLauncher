"""Run every check. No pytest, no console, no network:

    python tests/run_all.py

The suites stub the console and Flet's page, so this is safe to run anywhere —
useful before a `flet build apk`, where a mistake costs a ten minute rebuild
and a sideload to find.
"""

import pathlib
import subprocess
import sys

SUITES = ("test_units.py", "test_flows.py", "test_paths.py", "test_boxart.py")


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    failed = []

    for suite in SUITES:
        print(f"\n{'=' * 52}\n  {suite}\n{'=' * 52}")
        result = subprocess.run([sys.executable, str(here / suite)])
        if result.returncode != 0:
            failed.append(suite)

    print(f"\n{'=' * 52}")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(SUITES)} suites passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
