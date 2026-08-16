This is the opensource project `absicht`

### Post implementation tasks
- After you finished a task, analyze and reflect on the last two changes you made. Identify potential improvements,
  optimizations that could enhance code quality, performance, readability or maintanability.


### Coding preferences
- Maintainability is a must.
- Keep things simple. `KISS` and follow the `YAGNI` mantra unless told otherwise.
- Typehints are useful, use them.
- Tests are good! Smoke tests, regression tests for feature deletions are not useful. Tests should be focused, not slop.
- Comments are a great way to clarify functionality and how code is used. Don't comment every line. Simple functions that are mostly self describing by the name do not need a doc string. More complex functions do. Also what the purpose of a class and what the purpose of a module is, is a good thing to document.
- Keep comments and documentation up to date! When making changes it's important to keep things in sync.

### Documentation
- Separate documentation for maintainers in docs/maintainers, for end users docs/users


### Verification
- `./scripts/verify.sh` runs every gate CI enforces. Run it before you call a change finished.
  CI runs the same script, so a clean run here means a green build: there is no second set of flags to be surprised by.
- Run `./scripts/verify.sh fast` while you work — formatting, lint, the type checker, the import
  contracts, the dependency check and bandit, in a few seconds. Keep the full run for before you commit.
- `./scripts/verify.sh quick` is what the commit hook runs and is meant to stay sub-second. Do not
  add anything to it.
- One check at a time when you are chasing one thing: `./scripts/verify.sh types`, `... test`, `... imports`.
  `./scripts/verify.sh --list` names them all.
- The run does not stop at the first failure, so read the whole summary. It ends with the command that
  re-runs only what failed. Fix the code; do not reach for the threshold.
- Mutation testing (`./scripts/verify.sh mutation`) takes minutes and is not in the default suite. Run it
  when you have changed tests, to find out whether they assert anything.
- If a gate is genuinely wrong, say so and explain why rather than loosening it quietly. Thresholds,
  the tools and the exceptions already granted are documented in `docs/maintainers/verification.md`.


### Committing
- Commit often, self contained changes with a good concise but comprehensive description of what the change in the commit is addressing.
- Always finish your tasks with a commit.
- When you do a commit make sure you thoroughly tested it: `./scripts/verify.sh` must pass first.
  The git hooks run it for you (`uv run pre-commit install`), but do not use them as the moment you
  first find out — a hook that fails on commit means you skipped a step.
- When you write tests, commit the tests first and follow up with the actual implementation.
  That way a reviewer can verify that you didn't cheat with your tests.
#### Worktrees
Use .worktrees/ to create worktrees if you need them
