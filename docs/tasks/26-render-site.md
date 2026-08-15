# 26 — `ab render`: the site (pages, traceability, gaps)

## Depends on
[20-build.md](20-build.md), [21-show.md](21-show.md) (reuses its element→
Markdown rendering), [22-list.md](22-list.md), [23-gaps.md](23-gaps.md),
[24-trace.md](24-trace.md).

## Spec
> Generate the read-only site: element pages, traceability, gaps, diagrams.
>
> - `--out DIR` default `.absicht/build/site`
> - `--serve` `--port N` local preview with rebuild on change
> - `--scope REF` render one subtree
>
> — [`../spec/cli.md`](../spec/cli.md#ab-render)

This task is the non-diagram half of `ab render`. Diagrams (`--overlay`,
`--format {svg,mermaid,d2}`) are [`27-render-diagrams.md`](27-render-diagrams.md)
— split because the two halves have genuinely different tooling and
determinism concerns, and because this half can land and be useful (a
browsable static site with no pictures) before the harder diagram-rendering
problem is solved.

## What to build

`src/absicht/render.py`:

- One HTML (or plain Markdown-rendered-to-HTML — pick one, static-site-
  generator-free is fine given README's stated "no editor, no canvas"
  scope) page per element, generated from the same resolved-neighbourhood
  data `ab show` computes — literally reuse
  [`21-show.md`](21-show.md)'s function, don't re-derive it, this is
  exactly the "everything downstream reads the built artifact" principle
  applied one level up.
- An index page listing all elements (grouping by kind is the obvious
  choice, matching `ab list`'s own grouping).
- A traceability page (or section) — likely a rendering of `ab trace`'s
  output for the elements worth showing paths for (requirements, at
  minimum, per the spec's own example chain "requirement to component to
  seam to decision"), reusing [`24-trace.md`](24-trace.md)'s traversal.
- A gaps page, reusing [`23-gaps.md`](23-gaps.md)'s worklist.
- `--scope REF`: restrict every page above to the subtree reachable from
  `REF` (via `contains`, primarily, plus whatever the `Index` from
  [`03-resolve.md`](03-resolve.md) makes cheap to filter by) — a
  component's own mini-site, useful for a packet or a review of one part of
  a larger system.
- `--serve --port N`: a minimal local HTTP server (Python's
  `http.server.ThreadingHTTPServer` over the `--out` directory is enough —
  no need for a real web framework given README's explicit "no product
  looking for a market" stance) with rebuild-on-change (a simple file-watch
  loop over the store's mtimes, polling on an interval, is proportionate;
  a full filesystem-events dependency is not required unless polling proves
  genuinely too slow for a store this size — start with polling).

## Out of scope

- No diagrams, no `--overlay`, no `--format svg|mermaid|d2` —
  [`27-render-diagrams.md`](27-render-diagrams.md).
- No client-side JS framework, no build step, no bundler — static files,
  generated once per `ab render` invocation (or per rebuild in `--serve`
  mode). This is a read-only site, per the command's own one-line
  description; keep it that plain.

## Tests

- Against `tests/fixtures/systems/clean/`: `ab render` produces one page per
  element, an index, and the site is internally link-consistent (every
  `<a href>` this task generates resolves to a file that exists in the
  output — a cheap, valuable smoke test that catches broken
  cross-page links without needing a browser).
- `--scope REF` produces a smaller site containing only the subtree,
  provable by checking which element pages exist in the output.
- `--serve` is at minimum tested for "starts, serves the index page,
  shuts down cleanly" — don't try to test the rebuild-on-change loop's
  timing in CI; that's a source of flaky tests for very little signal. A
  unit test on the "did the store change since last render" detection
  function, decoupled from the actual server loop, is more valuable and
  more stable.

## Definition of done

- `absicht.render` added to the import-linter layers list.
- `tests/test_cli.py`: `render` stays in the "not implemented"
  parametrization until [`27-render-diagrams.md`](27-render-diagrams.md)
  also lands, since it's one CLI command backed by two tasks — coordinate
  with whoever picks up 27, or land both before flipping the test.
- `./scripts/verify.sh` clean.
