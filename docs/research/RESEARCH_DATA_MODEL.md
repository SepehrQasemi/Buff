# RESEARCH_DATA_MODEL

## Objective
Define a file-compatible, implementation-agnostic data model for S7 personal research workflows.

## Design Constraints
- Single-user scope.
- File-based compatible with S6.
- No database technology assumptions.
- Deterministic serialization and stable ordering requirements.

## Core Entities

### Experiment
- Represents one canonical research batch definition.
- Key fields:
  - `experiment_id`
  - `schema_version`
  - `name`
  - `hypothesis`
  - `dataset_id`
  - `strategy_id`
  - `parameter_grid`
  - `ranking_policy`
  - `created_at_utc`
  - `stage_token`

### Experiment Run Link
- Connects one parameter candidate to one produced run.
- Key fields:
  - `experiment_id`
  - `candidate_id`
  - `params`
  - `run_id`
  - `status`
  - `error_code`
  - `artifact_refs`

### Tag
- Freeform but normalized labels for retrieval and grouping.
- Key fields:
  - `tag`
  - `scope` (`experiment|run|note`)
  - `target_id`
  - `created_at_utc`

### Note
- Researcher-authored context attached to experiment or run.
- Key fields:
  - `note_id`
  - `scope`
  - `target_id`
  - `text`
  - `tags`
  - `created_at_utc`
  - `updated_at_utc`

### Ranking Entry
- Stores one ranked candidate result for an experiment.
- Key fields:
  - `experiment_id`
  - `rank`
  - `candidate_id`
  - `run_id`
  - `score`
  - `metrics_snapshot`
  - `tie_break_trace`

## File-Compatible Layout (Logical)
- `experiments/<experiment_id>/experiment_manifest.json`
- `experiments/<experiment_id>/experiment_registry.json`
- `experiments/<experiment_id>/ranking.json`
- `experiments/<experiment_id>/analysis_summary.json`
- `experiments/<experiment_id>/notes.jsonl`
- `experiments/<experiment_id>/tags.json`

## Determinism Rules
- IDs are validated and normalized.
- Lists with ordering semantics use stable deterministic sort policies.
- Canonical JSON serialization is required for manifest/registry/ranking artifacts.
- Note and tag records include explicit timestamps and stable IDs.
- Derived rankings are reproducible from linked run artifacts.

## Validation Rules
- Missing required fields fail closed.
- Unknown critical fields fail closed unless explicitly version-allowed.
- `run_id` link targets must reference existing run artifacts.
- Tag and note scopes must reference valid target IDs.
