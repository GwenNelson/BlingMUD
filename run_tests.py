#!/usr/bin/env python3

import os
import subprocess
import sys


TEST_TIMEOUT_SECONDS = 30
REPOSITORY_ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_TEMP_ROOT = os.path.join(REPOSITORY_ROOT, ".test-tmp")
TEST_COMMAND = (
    sys.executable,
    "-m",
    "unittest",
    "discover",
    "-s",
    "tests",
    "-p",
    "test_*.py"
)


def main():
    if os.path.islink(TEST_TEMP_ROOT):
        sys.stderr.write("Refusing to use a symlinked test temp directory.\n")
        return 2

    os.makedirs(TEST_TEMP_ROOT, exist_ok=True)

    if os.path.commonpath(
        (REPOSITORY_ROOT, os.path.realpath(TEST_TEMP_ROOT))
    ) != REPOSITORY_ROOT:
        sys.stderr.write("Test temp directory escapes the repository.\n")
        return 2

    environment = os.environ.copy()
    environment["TMPDIR"] = TEST_TEMP_ROOT
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    for unsafe_setting in (
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PYTHONSTARTUP"
    ):
        environment.pop(unsafe_setting, None)

    try:
        completed = subprocess.run(
            TEST_COMMAND,
            cwd=REPOSITORY_ROOT,
            env=environment,
            timeout=TEST_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "Test suite exceeded {0} seconds and was terminated.\n".format(
                TEST_TIMEOUT_SECONDS
            )
        )
        return 124

    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
