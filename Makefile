# Shorthand for scripts/verify.sh, which is where the checks are actually
# defined. Nothing here may add a flag of its own: local runs, the git hooks
# and CI have to be running the same commands.

.DEFAULT_GOAL := help
.PHONY: help verify quick fast all mutation format format-check \
	lint types imports deps security complexity quality test

help:
	@echo "make verify        every gate CI enforces, except mutation testing"
	@echo "make quick         the pre-commit subset: format, lint"
	@echo "make fast          quick plus types, imports, deps, security"
	@echo "make all           verify plus mutation testing (minutes, not seconds)"
	@echo "make format        rewrite the code to satisfy the formatter"
	@echo
	@echo "One check at a time: $(filter-out format,$(shell ./scripts/verify.sh --list))"

verify:
	./scripts/verify.sh

quick:
	./scripts/verify.sh quick

fast:
	./scripts/verify.sh fast

all:
	./scripts/verify.sh all

# The only target that changes files.
format:
	uv run ruff format src tests scripts

format-check lint types imports deps security complexity quality test mutation:
	./scripts/verify.sh $(patsubst format-check,format,$@)
