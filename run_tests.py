#!/usr/bin/env python3

import subprocess
import sys


TEST_TIMEOUT_SECONDS = 30
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
    try:
        completed = subprocess.run(
            TEST_COMMAND,
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
