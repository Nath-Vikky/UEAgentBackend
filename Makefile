.PHONY: dev test lint rag-eval docker-up docker-down docker-logs

dev:
	python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:
	python -m pytest tests/unit tests/contract tests/eval tests/integration

lint:
	python -m ruff check app tests scripts

rag-eval:
	python scripts/run_rag_eval.py --source-path ../backend.md --source-path ./docs --source-path ./knowledge --top-k 4 --min-hit-at-k 0.25 --min-route-accuracy 0.75

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f app
