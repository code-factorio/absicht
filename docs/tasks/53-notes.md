# 53 — Notes: storage and `ab note`

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md),
[51-model-behaviors-resources.md](51-model-behaviors-resources.md).

## Goal

The capture channel. One task end-to-end — storage, loading, and the whole
`ab note` group — because notes' defining property is what they are *excluded*
from, and that exclusion is easiest to keep honest when one change builds the
inclusion and the exclusion together.

## Spec

> **Not an element.** Notes are not in the resolved graph, carry no state,
> are referenced by nothing, and […] **Notes are never packet input. An
> agent never sees a note.** […] **Capture friction must be near zero.** […]
> Terminal states are **promoted** […] or **dropped**. […] Age is surfaced,
> not just count. […] **Notes are committed.** They live in `.absicht/notes/`.
>
> — [addendum §6](../spec/ABSICHT-MODEL-ADDENDUM.md#6-note)

The CLI surface is `ab note add / list / show / promote / drop` —
[`../spec/cli.md`](../spec/cli.md#ab-note).

## What to build

- `absicht.codec` / `absicht.load`: read and write `notes/<slug>.md`
  (front matter `id`, optional `ref`, `created`, optional `promoted_to`;
  Markdown body). `LoadedStore` grows a `notes` collection. Notes never
  enter `Design` — enforce with a test, not a comment.
- `absicht.notes` (new module, layered with `new`/`init`): `add`, `promote`,
  `drop` operations, id generation per `50-addendum-conventions.md`
  (`note:` + six random base36 chars, collision-checked). `promote` creates
  the target element through the same machinery `ab new` uses, then rewrites
  the note with `promoted_to` set. `drop` deletes the file. `promote` on an
  already-promoted note and `drop` on a promoted note are `USAGE` errors —
  the record of what a note became must survive.
- `ab note` command group in the CLI:
  - `add [TEXT]` — body from argument, else stdin (piped), else `--edit`.
    `--ref REF` optional; a ref that doesn't parse as a `Ref` is `USAGE`,
    but an unresolvable one is *accepted* (capture first; the check rule
    reports it later — friction rule).
  - `list` — the inbox: unpromoted notes, oldest first, each with age;
    header line surfaces "N notes, oldest X" (§6: age is pressure, count is
    not). `--ref REF`, `--all`, `--format {text,json,ids}`.
  - `show ID`, `promote ID KIND SLUG`, `drop ID`.
  - `--json` per the standard envelope; `created` is authored at add time
    (today), which is fine — determinism constraints apply to builds, not
    to authoring commands (`ab new` has the same property).
- The check rule `integrity/note-promoted-to-unresolvable` — it lives with
  the note loader's consumer, and 54 should not need to re-learn note
  loading. Register the rule id; notes are otherwise exempt from graph
  validation *by construction* (they are simply not in the walk).

## Out of scope

- Packet exclusion — nothing to do: notes are not in `Design`, so
  [57](57-packet-behaviors.md) cannot include them; that task asserts it.
- Site rendering of the inbox — [60](60-addendum-render.md).
- Any notion of note kinds, owners, or classification — the addendum forbids
  it. If a field feels missing, the answer is promotion, not a field.

## Tests

- `add` with argument / stdin / `--edit` (mock the editor) each produce a
  parseable committed file; generated ids never collide with existing ones
  (seed the store with a colliding file and watch it re-draw).
- `promote` creates the element, stamps `promoted_to`, and the note leaves
  `list` (but appears under `--all`); `drop` removes the file; both refuse
  a promoted note appropriately.
- `list` ordering and the age header; `--json` envelope carries
  `schema_version`.
- A store with a `notes/` directory builds a `Design` with no trace of
  them; `ab check` on a note with a bad `promoted_to` yields exactly the
  one registered rule.

## Definition of done

- `absicht.notes` in the import-linter layers list, same commit.
- `tests/test_cli.py` `SURFACE` updated for the new group (flag-presence
  test included), per `00-conventions.md`.
- `./scripts/verify.sh` clean.
