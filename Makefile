.PHONY: help install run-backend run-frontend test clean

help:
	@echo "Voice Agent - Available Commands:"
	@echo "  install        - Install all dependencies (backend + frontend)"
	@echo "  run-backend    - Start FastAPI backend server"
	@echo "  run-frontend   - Start React frontend dev server"
	@echo "  test          - Run all tests"
	@echo "  clean         - Clean build artifacts"
	@echo "  setup         - Complete project setup"

install: install-backend install-frontend

install-backend:
	cd backend && poetry install

install-frontend:
	cd frontend && npm install

run-backend:
	cd backend && poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-frontend:
	cd frontend && npm start

test: test-backend test-frontend

test-backend:
	cd backend && poetry run pytest

test-frontend:
	cd frontend && npm test -- --watchAll=false

clean:
	cd backend && rm -rf __pycache__ .pytest_cache
	cd frontend && rm -rf build node_modules/.cache

setup: install
	@echo "Setup complete! Run the following commands in separate terminals:"
	@echo "  make run-backend"
	@echo "  make run-frontend"