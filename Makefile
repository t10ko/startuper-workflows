.PHONY: verify lint test fmt clean

# The standalone repo's own verify command. Consumer repos set their own
# verify command in .agents/config.toml ([project] verify_cmd); workflows
# read it from there, never from this file.
verify: lint test
	@echo "verify: OK"

lint:
	uv run ruff check src hooks scripts tests

test:
	uv run pytest tests

fmt:
	uv run ruff check --fix src hooks scripts tests

clean:
	rm -rf .pytest_cache .ruff_cache src/agentic_workflows/__pycache__ hooks/__pycache__ scripts/__pycache__ tests/__pycache__
