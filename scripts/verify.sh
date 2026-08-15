#!/usr/bin/env bash
#
# The verification suite. Every gate CI enforces is defined here and nowhere
# else, so a local run and a CI run cannot drift apart.
#
#   scripts/verify.sh                 the full suite: everything except mutation
#   scripts/verify.sh quick           what the pre-commit hook runs, sub-second
#   scripts/verify.sh fast            quick, plus the checks that answer in seconds
#   scripts/verify.sh all             the full suite plus mutation testing
#   scripts/verify.sh types test      named checks only
#   scripts/verify.sh --list          list the checks
#
# Checks run to completion even after one fails, so a single run tells you
# everything that is wrong. Exit status is non-zero if any check failed.

set -uo pipefail

cd "$(dirname "$0")/.."

# Percentage of killed mutants (of killed + survived) the suite must reach.
# Raise it as the tests improve. Never lower it to make a branch pass.
: "${MUTATION_FLOOR:=45}"

# Each suite is the one below it plus what it can afford to add, so a new check
# has to be named exactly once: here, next to its `check_` function.
#
# QUICK is the commit hook and is the one budget that is not negotiable: the
# moment committing costs four seconds people reach for --no-verify and the
# whole mechanism is gone.
QUICK=(format lint)
FAST=("${QUICK[@]}" types imports deps security)
FULL=("${FAST[@]}" complexity quality test)
CHECKS=("${FULL[@]}" mutation)

# --- checks ----------------------------------------------------------------
# One function per check. Each is silent about how it is wired up: it just runs
# the tools and returns their status.

check_format() {
	uv run ruff format --check src tests scripts
}

check_lint() {
	uv run ruff check src tests scripts
}

# One type checker gates the build. pyright is configured in pyproject.toml for
# the editor's language server, and deliberately not run here: the marginal
# catch rate of a second checker does not pay for a second set of ignore
# comments on every push. See CONTEXT.md.
check_types() {
	uv run mypy
}

# The layer contract is the rule that keeps the file format swappable and the
# core reusable behind a web or MCP surface. Enforced, not asserted.
check_imports() {
	uv run lint-imports
}

check_deps() {
	uv run deptry src
}

check_security() {
	uv run bandit -c pyproject.toml -q -r src/absicht
}

# A smoke alarm, not a design tool: agents grow functions rather than
# refactoring them, so a ceiling is a forcing function they respond to. It
# stays loose because resolve and check will legitimately be branchy.
check_complexity() {
	uv run xenon --max-average A --max-modules B --max-absolute E src/absicht
}

# Clone detection is the reason this is here: copy-paste-and-tweak is locally
# safe and globally corrosive, and no other tool in the suite sees it.
check_quality() {
	uv run pyscn check --max-complexity 15 src/absicht
}

check_test() {
	uv run pytest --cov=absicht --cov-report=term-missing
}

# The modules where a silent wrong answer is the whole failure mode: a packet
# that quietly drops a `must_hold` ADR passes every other check in this file.
# Everything else — the CLI, the renderer — is not worth the runtime.
MUTATION_SCOPE=(src/absicht/model src/absicht/check.py src/absicht/packet.py)

# Mutation testing takes minutes, not seconds, and it is the most valuable tool
# here: it is the only one that answers "do these tests assert anything", which
# is exactly how agent-written tests fail. It is not part of the default suite;
# CI runs it nightly and you run it here when you have changed tests.
check_mutation() {
	local path present=()
	for path in "${MUTATION_SCOPE[@]}"; do
		[[ -e $path ]] && present+=("$path")
	done
	if [[ ${#present[@]} -eq 0 ]]; then
		echo "mutation: nothing in scope yet — none of ${MUTATION_SCOPE[*]} exist."
		echo "mutation: this check arms itself when they land; see docs/maintainers/verification.md."
		return 0
	fi

	rm -f mutants/mutmut-cicd-stats.json
	uv run mutmut run || return 1
	uv run mutmut export-cicd-stats || return 1
	uv run python scripts/mutation_score.py \
		mutants/mutmut-cicd-stats.json \
		--floor "$MUTATION_FLOOR"
}

# --- runner ----------------------------------------------------------------

# The header comment of this file is the usage text.
usage() {
	awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"
}

resolve() {
	case "$1" in
	quick) printf '%s\n' "${QUICK[@]}" ;;
	fast) printf '%s\n' "${FAST[@]}" ;;
	full) printf '%s\n' "${FULL[@]}" ;;
	all) printf '%s\n' "${CHECKS[@]}" ;;
	*)
		if [[ " ${CHECKS[*]} " == *" $1 "* ]]; then
			printf '%s\n' "$1"
		else
			echo "verify: unknown check or suite: $1" >&2
			echo "verify: try one of: quick fast full all ${CHECKS[*]}" >&2
			return 1
		fi
		;;
	esac
}

main() {
	local requested=()
	case "${1-}" in
	--list) printf '%s\n' "${CHECKS[@]}"; return 0 ;;
	-h | --help) usage; return 0 ;;
	esac

	local name resolved one
	if [[ $# -eq 0 ]]; then
		requested=("${FULL[@]}")
	else
		for name in "$@"; do
			resolved=$(resolve "$name") || return 2
			while read -r one; do
				requested+=("$one")
			done <<<"$resolved"
		done
	fi

	if ! command -v uv >/dev/null; then
		echo "verify: uv is not installed - see https://docs.astral.sh/uv/" >&2
		return 2
	fi

	local failed=() started elapsed status
	for name in "${requested[@]}"; do
		echo
		echo "=== $name"
		started=$SECONDS
		"check_$name"
		status=$?
		elapsed=$((SECONDS - started))
		if [[ $status -eq 0 ]]; then
			echo "--- $name ok (${elapsed}s)"
		else
			echo "--- $name FAILED (${elapsed}s)"
			failed+=("$name")
		fi
	done

	echo
	if [[ ${#failed[@]} -eq 0 ]]; then
		echo "verify: ${#requested[@]} check(s) passed"
		return 0
	fi
	echo "verify: ${#failed[@]} of ${#requested[@]} check(s) failed: ${failed[*]}"
	echo "verify: re-run just those with: scripts/verify.sh ${failed[*]}"
	return 1
}

main "$@"
