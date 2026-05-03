import os
import sys


def run():
    os.system("uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")


def migrate():
    os.system("alembic upgrade head")


def makemigration():
    msg = sys.argv[2] if len(sys.argv) > 2 else "migration"
    os.system(f'alembic revision --autogenerate -m "{msg}"')


def test():
    os.system("pytest -v")


def lint():
    os.system("ruff check .")


def format_code():
    os.system("black .")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/dev.py <command> [args]")
        sys.exit(1)

    command = sys.argv[1]
    commands = {
        "run": run,
        "migrate": migrate,
        "makemigration": makemigration,
        "test": test,
        "lint": lint,
        "format": format_code,
    }

    if command not in commands:
        print(f"Unknown command '{command}'. Available: {', '.join(commands)}")
        sys.exit(1)

    commands[command]()
