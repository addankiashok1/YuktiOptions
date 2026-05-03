import os
import sys

def run():
    os.system("uvicorn app.main:app --reload")

def migrate():
    os.system("alembic upgrade head")

def makemigration():
    msg = sys.argv[2] if len(sys.argv) > 2 else "migration"
    os.system(f'alembic revision -m "{msg}"')

def test():
    os.system("pytest")

def lint():
    os.system("ruff check .")

def format():
    os.system("black .")

if __name__ == "__main__":
    command = sys.argv[1]

    if command == "run":
        run()
    elif command == "migrate":
        migrate()
    elif command == "makemigration":
        makemigration()
    elif command == "test":
        test()
    elif command == "lint":
        lint()
    elif command == "format":
        format()
    else:
        print("Invalid command")