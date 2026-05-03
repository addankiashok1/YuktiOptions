.PHONY: run migrate makemigration lint format test docker-up docker-down clean

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic upgrade head

makemigration:
	@test -n "$(msg)" || (echo "Usage: make makemigration msg='your message'" && exit 1)
	alembic revision --autogenerate -m "$(msg)"

lint:
	ruff check .

format:
	black .

test:
	pytest -v

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
