# Changelog

All notable changes to `branching-story-mcp` are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-27

### Added

- MCP server over stdio (JSON-RPC 2.0) for protocol versions `2024-11-05` and
  `2025-03-26`: `initialize`, `notifications/initialized`, `ping`, `tools/list`,
  `tools/call`, `resources/list`, `resources/read`.
- Tool `validate_story_graph` — schema validation, missing-target detection,
  unreachable scenes, dead ends, loop traps and invalid guard predicates.
- Tool `step_story_state` — deterministic reducer with `set` / `add` / `append`
  effects, guard evaluation, turn-stamped memory log and a verifiable SHA-256
  trace hash.
- Tool `query_ai_story_benchmark` — verified Nov 15 2026 10-platform consumer AI
  story continuity matrix (doi:10.7910/DVN/YEBHQR) with APA/BibTeX citation.
- Tool `detect_state_drift` — deterministic recall / contradiction / omission
  classification against the five-mode silent state drift taxonomy
  (doi:10.5281/zenodo.24549412).
- Resources `ouba://benchmark/2026-10-platform-matrix` (CC-BY-4.0) and
  `ouba://schema/story-graph-v1`.
- Zero-dependency Python package (stdlib only, Python >= 3.10) with console
  script `branching-story-mcp`.
- Zero-dependency Node/ESM mirror (Node >= 18) with JSR manifest
  `@ouba-studio/branching-story-mcp`.
- Official MCP Registry `server.json` manifest
  (`io.github.ouba-studio/branching-story-mcp`).
- Full stdio test suites for both runtimes.
