"""Run the tests without pytest: python -m tests

pytest collects these same files if you have it; this runner exists so
that a fresh clone can check itself with nothing installed, which is the
same reason provider.py speaks urllib instead of requests.
"""

import importlib
import sys
import traceback

MODULES = ("tests.test_tools", "tests.test_security", "tests.test_context",
           "tests.test_memory", "tests.test_skills", "tests.test_session",
           "tests.test_subagent", "tests.test_harness")


def main():
    """Run every test_* function in every module; return the failure count."""
    failures = []
    for name in MODULES:
        module = importlib.import_module(name)
        print(f"\n{name}")
        for attr in sorted(vars(module)):
            if not attr.startswith("test_"):
                continue
            try:
                getattr(module, attr)()
                print(f"  PASS  {attr}")
            except Exception:
                failures.append(f"{name}.{attr}")
                print(f"  FAIL  {attr}")
                print(traceback.format_exc(limit=3).rstrip())
    print(f"\n{'ALL PASS' if not failures else f'{len(failures)} FAILED: {failures}'}")
    return len(failures)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
