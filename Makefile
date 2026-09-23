.PHONY: verify lint test fmt clean

# The standalone repo's own verify command. Consumer repos set their own
# verify command in .agents/config.toml ([project] verify_cmd); workflows
# read it from there, never from this file.
verify: lint test
	python3 tools/check_stdlib_only.py
	@echo "verify: OK"

lint:
	uv run ruff check agentic_workflows .agents/hooks .agents/scripts tests

test:
	uv run pytest tests

fmt:
	uv run ruff check --fix agentic_workflows .agents/hooks .agents/scripts tests

clean:
	rm -rf .pytest_cache .ruff_cache agentic_workflows/__pycache__ .agents/hooks/__pycache__ .agents/scripts/__pycache__ tests/__pycache__
