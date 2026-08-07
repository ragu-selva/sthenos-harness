"""Day 5 -- final mechanical verification only, after both phases finished across two
API credit outages and manual resumes. See day5_ship_products.py for the checks
themselves; this just re-runs them and prints the results table.
"""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

spec = importlib.util.spec_from_file_location(
    "day5_ship_products", os.path.join(os.path.dirname(os.path.abspath(__file__)), "day5_ship_products.py"))
ship = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ship)


def main():
    workdirs = {name: os.path.join(ship.PRODUCTS_DIR, name) for name in ship.PROJECTS}
    checks_by_project = {
        "artisan-coffee": ship.verify_artisan_coffee(workdirs["artisan-coffee"]),
        "taskman": ship.verify_taskman(workdirs["taskman"]),
        "viper": ship.verify_viper(workdirs["viper"]),
    }

    print(f"{'project':<16}{'pass/fail':<10}{'turns':<8}checks")
    for name, checks in checks_by_project.items():
        visible = {k: v for k, v in checks.items() if not k.startswith("_")}
        passed = all(visible.values())
        turns = ship.count_turns(workdirs[name])
        print(f"{name:<16}{'PASS' if passed else 'FAIL':<10}{turns:<8}")
        for k, v in visible.items():
            print(f"    [{'x' if v else ' '}] {k}")
        if "_test_tail" in checks:
            print(f"    -- unittest tail --")
            print("    " + checks["_test_tail"].replace("\n", "\n    "))


if __name__ == "__main__":
    main()
