"""Запускает все проверки AI Limits (их же вызывает build_exe.cmd перед сборкой).

    python tests\run_tests.py

Проверки работают на вымышленных данных; окно программы открывается на несколько секунд.
Код возврата 0 — всё прошло."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ("test_backend.py", "test_gui.py")


def main():
    failed = []
    for name in TESTS:
        code = subprocess.call([sys.executable, os.path.join(HERE, name)])
        if code:
            failed.append(name)
    print("ПРОВЕРКИ НЕ ПРОШЛИ: " + ", ".join(failed) if failed else "Все проверки пройдены.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
