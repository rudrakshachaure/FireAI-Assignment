
import sys
import subprocess
import os
from pathlib import Path

# Project directory
PROJECT_DIR = Path(__file__).resolve().parent

def run(command, description):
    print("\n" + "=" * 60)
    print(description)
    print("=" * 60)

    subprocess.run(
        command,
        cwd=PROJECT_DIR,
        check=True
    )

def main():

    # 1. Create virtual environment
    print("Creating virtual environment...")

    subprocess.run(
        [sys.executable, "-m", "venv", ".venv"],
        cwd=PROJECT_DIR,
        check=True
    )

    # 2. Find virtual environment Python
    python = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"

    # 3. Upgrade pip
    run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip"],
        "Upgrading pip"
    )

    # 4. Install dependencies
    run(
        [str(python), "-m", "pip", "install", "-r", "requirements.txt"],
        "Installing project dependencies"
    )

    # 5. Run tests
    run(
        ["make", "test"],
        "Running unit tests"
    )

    # 6. Run quick trial
    run(
        ["make", "all", "PER_MONTH_LIMIT=20000"],
        "Running Project B - Quick Trial"
    )

    print("\nPROJECT COMPLETED SUCCESSFULLY!")
    print("Check eval/out/ for CSV results.")

if __name__ == "__main__":
    main()
