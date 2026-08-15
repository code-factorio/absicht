# `--json` is accepted on the command, not only ahead of it

Click only parses a group's options before the subcommand name, so the surface
spec's global `--json` meant `ab --json check` and made `ab check --json` a
usage error. That is the wrong way round for the caller the flag exists for:
agents and CI append flags to a command they have composed, and every other CLI
they have seen accepts them there. So every command declares `--json` as well,
`absicht.cli._common.options` or-s the two into one `GlobalOptions.json_output`,
and both positions — or both at once — mean the same thing.

## Consequences

The fold keys off the parameter name: a command must spell it `json_output` or
it will accept the flag and silently ignore it. `JsonOption` in `_common.py`
carries the type, and a test parametrized over the whole surface catches the
name.

Where a command also has `--format` with a `json` member, the two overlap. The
rule for the bodies, when they land: an explicitly passed `--format` wins, and
`--json` selects the json member only when `--format` was left at its default
(`click.core.ParameterSource.DEFAULT` distinguishes the two). `--json` is a
shorthand, never an override.

Only `--json` gets this treatment. `--store` and `--rev` are equally positional
but nobody has been bitten by them yet, and twenty commands re-declaring six
flags each is a worse problem than the one being solved. Revisit per flag, when
it stings.
