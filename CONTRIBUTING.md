# Contributing to Buff

Thanks for contributing! Keep changes focused and deterministic.

## Setup
- Python 3.10+
- Install dev dependencies:
  - `python -m pip install -e ".[dev]"`

## Quality gates
- Run lint: `ruff check .`
- Run tests: `pytest -q`

## Branch naming
- Use: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`, `docs/<topic>`

## Pull requests
- Keep PRs small and scoped.
- Describe impact and risks.
- Ensure CI passes and docs updated if needed.

## Determinism & safety
- No network calls in tests.
- No non-deterministic output (time, randomness) unless mocked/frozen.
