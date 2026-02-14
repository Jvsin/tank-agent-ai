"""
Runner trudniejszych testów agenta.

Nie zastępuje run_agent_tests.py — to osobny, cięższy pakiet do regressji jakości ruchu.
"""

import os
import subprocess
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

TEST_FILES = [
    "test_agent_real_map_hard.py",
    "test_agent_map_trap_scenarios.py",
]


def main() -> int:
    python_exe = sys.executable
    failures = 0

    for test_file in TEST_FILES:
        path = os.path.join(THIS_DIR, test_file)
        print(f"\n=== RUN {test_file} ===")
        result = subprocess.run([python_exe, path], cwd=THIS_DIR)
        if result.returncode != 0:
            failures += 1
            print(f"=== FAIL {test_file} (code={result.returncode}) ===")
        else:
            print(f"=== PASS {test_file} ===")

    if failures:
        print(f"\nAGENT HARD TESTS: FAIL ({failures} failed)")
        return 1

    print("\nAGENT HARD TESTS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
