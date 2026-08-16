# 54 — Check: the addendum's rules

## Depends on
[00-conventions.md](00-conventions.md),
[50-addendum-conventions.md](50-addendum-conventions.md),
[52-store-wiring.md](52-store-wiring.md),
[53-notes.md](53-notes.md) (only for the note rule's registration — if 53
landed it there already, this task just confirms coverage).

## Goal

Every **Check rule** line the addendum states, as `ab check` findings with
registered ids, `--explain` text, and a fixture that trips each one plus one
that does not. The rule table — ids, severities, and which rules are
subsumed by existing machinery — is pinned in
[`50-addendum-conventions.md`](50-addendum-conventions.md#check-rule-ids);
this task implements it, it does not re-derive it.

## Spec

> **Check rule:** a seam referencing a resource is an error. — §1.4
>
> **Check rules:** a behavior with no observations is an error. A
> requirement with no behavior realizing it is a warning, not an error. — §2
>
> **`timing` is omitted for `must_not`** and its presence is a check error.
> — §3.1
>
> **Check rule:** `at` must resolve. An `at` pointing at a requirement,
> decision, question or note is an error. — §3.2
>
> **Cycles are an error.** `ab check` already walks the graph for
> `blocked_by` and `depends_on`; behavior composition joins that walk. — §4.2
>
> **Check rules:** `supersedes` must resolve; a behavior may not supersede
> itself; supersession chains may not cycle. A `superseded` behavior
> appearing in a milestone's must-satisfy set is an error. — §5
>
> **Check rule:** `promoted_to` must resolve when present. — §6
>
> — [../spec/ABSICHT-MODEL-ADDENDUM.md](../spec/ABSICHT-MODEL-ADDENDUM.md)

## What to build

In `src/absicht/check.py`, following the existing three-layer shape and the
`RULES.update(...)` registration style (each description says what, and why
its severity is what it is — read the existing entries for the register):

- **Integrity:**
  - `integrity/seam-references-resource` — any `resource:` ref in a Seam's
    ref fields (`provider`, `consumers`, `carries`). A component's
    relationship to a resource is a dependency, not a contract.
  - `integrity/observation-at-wrong-kind` — `at` whose kind prefix is
    `requirement`, `decision`, `question` (or `note`, which cannot resolve
    anyway — fold into the message). Allowed: component, resource, seam,
    behavior (§3.2).
  - `integrity/composition-cycle` — observations whose `at` is a
    `behavior:` ref form a directed graph; join the existing `_cycles`
    walk. One finding per distinct cycle, like `integrity/cycle`.
  - `integrity/supersession-cycle` — same walk over `supersedes`;
    self-supersession is the length-1 case, same rule id.
  - Resolution of `observation.at` and `supersedes` should already fall out
    of `iter_references` + `integrity/dangling-ref`
    ([52](52-store-wiring.md)); register
    `integrity/observation-at-unresolvable` / `integrity/supersedes-unresolvable`
    as handled-upstream entries (the `integrity/criteria-anchored`
    precedent) rather than duplicating the walk — `--explain` must answer
    for every id the spec implies.
- **Schema:** `schema/must-not-has-timing` — handled upstream by the
  `Observation` validator from [51](51-model-behaviors-resources.md);
  register it so `--explain` answers.
- **Policy:**
  - `policy/behavior-needs-observations` — error. Applies regardless of
    `lifecycle`; a superseded behavior with no observations was always
    broken.
  - `policy/requirement-needs-behavior` — warn: no active behavior's
    `realizes` names the requirement. Mirror the tone of
    `policy/requirement-needs-realizer` (incomplete but honest).
  - `policy/superseded-in-must-satisfy` — error: a milestone's `includes`
    names a behavior whose `lifecycle` is `superseded`. It stopped being
    packet input; selecting it is a contradiction.

## Out of scope

- Deriving `superseded_by` or scope — [56](56-derived-scope-composition.md).
  The cycle walks here read stored fields only.
- Any `ab verify` behavior — verification of observations is
  [59](59-verify-observations.md); `check` asks whether the design is
  well-formed, never whether code satisfies it.

## Tests

- Per rule: one fixture element that trips it, one adjacent that does not
  (CONTEXT.md: "every validation rule needs a fixture that trips it and one
  that does not"). The `broken` fixture extensions from
  [52](52-store-wiring.md) carry most trip wires; add what is missing.
- Severity and exit code: the warning rule alone exits `0` without
  `--strict`, `1` with; each error rule exits `FINDINGS`.
- `--explain` answers for every id in the pinned table, including the
  handled-upstream ones.

## Definition of done

- `./scripts/verify.sh` clean; consider `verify.sh mutation` — this task is
  almost entirely branchy rule logic, exactly what mutation testing exists
  to keep honest.
