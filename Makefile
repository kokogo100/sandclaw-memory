.PHONY: format lint typecheck test test-cov check build publish clean

# ─── Code Quality ───
format:
	ruff format sandclaw_memory tests examples

lint:
	ruff check sandclaw_memory tests examples

typecheck:
	pyright sandclaw_memory

# ─── Testing ───
test:
	pytest -v

test-cov:
	pytest --cov=sandclaw_memory --cov-report=term-missing

# ─── All checks (run before committing) ───
check: format lint typecheck test

# ─── Build & Publish ───
build: clean
	python -m build

publish: build
	twine upload dist/*

clean:
	rm -rf dist/ build/ *.egg-info sandclaw_memory.egg-info
