"""Day 5 -- phase 2 only: review-and-fix + mechanical verification.

Companion to day5_ship_products.py, split out because phase 1 needed a
manual detour (a corrective resume for two of the three projects after an
API credit outage interrupted the first attempt -- see
day5_ship_products_continue.py). All three builds are done now; this picks
up at the review pass exactly as day5_ship_products.main() would have.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import importlib.util

spec = importlib.util.spec_from_file_location(
    "day5_ship_products", os.path.join(os.path.dirname(os.path.abspath(__file__)), "day5_ship_products.py"))
ship = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ship)


def main():
    workdirs = {name: os.path.join(ship.PRODUCTS_DIR, name) for name in ship.PROJECTS}

    print("=== PHASE 2: review as a demanding design director, fix, verify ===")
    review_results = ship.run_review_phase(workdirs)
    for r in review_results:
        print(f"\n--- review/{r['name']} ok={r['ok']} ---\n{ship._clip(r['report'], 1500)}")

    print("\n=== mechanical verification ===")
    checks_by_project = {
        "artisan-coffee": ship.verify_artisan_coffee(workdirs["artisan-coffee"]),
        "taskman": ship.verify_taskman(workdirs["taskman"]),
        "viper": ship.verify_viper(workdirs["viper"]),
    }

    print("\n=== RESULTS ===")
    print(f"{'project':<16}{'pass/fail':<10}{'turns':<8}checks")
    for name, checks in checks_by_project.items():
        visible = {k: v for k, v in checks.items() if not k.startswith("_")}
        passed = all(visible.values())
        turns = ship.count_turns(workdirs[name])
        print(f"{name:<16}{'PASS' if passed else 'FAIL':<10}{turns:<8}")
        for k, v in visible.items():
            print(f"    [{'x' if v else ' '}] {k}")
        if "_test_tail" in checks:
            print(f"    test output tail:\n{checks['_test_tail']}")

    return checks_by_project


if __name__ == "__main__":
    main()
