.PHONY: dev test lint review rag-eval benchmark code-review-benchmark docker-up docker-down docker-logs

dev:
	python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:
	python -m pytest tests/unit tests/contract tests/eval tests/integration

lint:
	python -m ruff check app tests scripts

review:
	python -m ruff check app tests scripts
	python -m compileall app
	python -m pytest tests/unit tests/contract tests/eval

rag-eval:
	python scripts/run_rag_eval.py --source-path ../backend.md --source-path ./docs --source-path ./knowledge --top-k 4 --min-hit-at-k 0.25 --min-route-accuracy 0.75

benchmark:
	python scripts/run_project_benchmark.py --output storage/artifacts/evals/project-benchmark-latest.json --markdown-output docs/benchmark-report.md

code-review-benchmark:
	python scripts/run_code_review_benchmark.py --min-recall 0.85 --min-precision 0.85

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f app
