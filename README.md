# branching-story-mcp

<!-- mcp-name: io.github.ouba-studio/branching-story-mcp -->

**A zero-dependency Model Context Protocol server that gives AI agents a deterministic
story-state kernel and the verified 2026 Consumer AI Story Continuity Benchmark.**

`branching-story-mcp` exposes [Ouba Studio](https://www.ouba.art/)'s
[`branching-story-kit`](https://github.com/ouba-studio/branching-story-kit) story-state
kernel and the CC-BY-4.0 [2026 Consumer AI Story Continuity Benchmark](https://doi.org/10.7910/DVN/YEBHQR)
directly to Claude Desktop, Claude Code, Cursor, Windsurf, Cline, Zed, VS Code, ChatGPT
and every other MCP client. Four tools, two resources, **zero runtime dependencies** —
pure Python stdlib (`>=3.10`) and pure Node ESM (`>=18`), behaviour-identical down to the
trace hash.

```text
uvx branching-story-mcp        # PyPI · no install step, no dependency bloat
npx @ouba-studio/branching-story-mcp   # npm · zero dependencies
deno run -A jsr.io/@ouba-studio/branching-story-mcp/server   # JSR
```

[![License: MIT](https://img.shields.io/badge/License-MIT-0b7a4b.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://pypi.org/project/branching-story-mcp/)
[![Node](https://img.shields.io/badge/node-18%2B-339933?logo=node.js&logoColor=white)](package.json)
[![MCP](https://img.shields.io/badge/MCP-2024--11--05%20%7C%202025--03--26-1F6FEB)](https://modelcontextprotocol.io/)
[![Dataset](https://img.shields.io/badge/dataset-10.7910%2FDVN%2FYEBHQR-9B1B31)](https://doi.org/10.7910/DVN/YEBHQR)
[![branching-story-mcp MCP server](https://glama.ai/mcp/servers/ouba-studio/branching-story-mcp/badges/score.svg)](https://glama.ai/mcp/servers/ouba-studio/branching-story-mcp)

---

## Why this exists

In the [2026 AI Story Apps Benchmark](https://www.ouba.art/i-tested-ai-story-apps)
(evaluation date `2026-11-15`), a trivial fact planted at turn 2 — *"My cat's name is
Marmalade."* — was **silently lost by turn 15** by a major product that stayed perfectly
fluent, on-persona and fast the whole time. Four products were right-censored by signup or
trial walls before the probe could even be administered.

`branching-story-mcp` is the deterministic answer: **explicit state, one write path, and a
memory log you can verify with a hash.** An agent that steps a story through this server
cannot drift — any divergence between the returned `trace_hash` and a locally recomputed
hash is proof that state was mutated outside the reducer.

The benchmark matrix ships inside the server, so an agent can *cite the evidence* while it
builds the story. Both are first-class MCP objects: tools for the kernel, a resource for the
data.

---

## Install

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "branching-story-mcp": {
      "command": "uvx",
      "args": ["branching-story-mcp"]
    }
  }
}
```

Or, if you prefer the Node build:

```json
{
  "mcpServers": {
    "branching-story-mcp": {
      "command": "npx",
      "args": ["-y", "@ouba-studio/branching-story-mcp"]
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "branching-story-mcp": {
      "command": "uvx",
      "args": ["branching-story-mcp"]
    }
  }
}
```

### Windsurf (`~/.codeium/windsurf/mcp_config.json`)

```json
{
  "mcpServers": {
    "branching-story-mcp": {
      "command": "uvx",
      "args": ["branching-story-mcp"]
    }
  }
}
```

### Cline / VS Code (`.vscode/mcp.json`)

```json
{
  "servers": {
    "branching-story-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["branching-story-mcp"]
    }
  }
}
```

### ChatGPT / remote MCP clients

The server is stdio-only and needs no credentials, no network access and no environment
variables. Put it behind any stdio-to-HTTP bridge (MCP Inspector, `supergateway`, or a
three-line proxy) and register the resulting Streamable HTTP endpoint with your client. It
is read-only: every tool is `readOnlyHint: true`, `destructiveHint: false`.

### Verify it in ten seconds

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | uvx branching-story-mcp
```

---

## Protocol compliance

JSON-RPC 2.0 over stdio, one JSON message per line, newline-delimited. Nothing is ever
written to stdout except responses.

| Method | Behaviour |
| :--- | :--- |
| `initialize` | Returns `protocolVersion` (echoes `2024-11-05` or `2025-03-26`), `capabilities`, `serverInfo`, `instructions` |
| `notifications/initialized` | Notification — no response |
| `ping` | `{}` |
| `tools/list` | 4 tools with JSON Schema `inputSchema`, `outputSchema` and annotations |
| `tools/call` | `{content:[{type:"text"}], structuredContent, isError}` |
| `resources/list` | 2 resources with URI, name, title, description, mimeType |
| `resources/read` | `{contents:[{uri, mimeType, text}]}` |
| `resources/templates/list` | `{resourceTemplates: []}` |
| `prompts/list` | `{prompts: []}` (no prompt capability advertised) |
| `logging/setLevel` | `{}` |
| anything else | `-32601 Method not found` |

Unknown tools and malformed arguments return `-32602`; semantic failures (a broken story
graph) return `isError: true` with a structured payload so the agent can repair its input.

---

## Tools

### 1. `validate_story_graph`

Validate a `branching-story-kit` scene graph before an agent writes a single line of prose.

**Input**

```json
{
  "story": {
    "id": "midnight-bookshop",
    "startScene": "arrival",
    "initialState": { "spark": 1, "trust": 1, "item": "cardamom tea" },
    "scenes": {
      "arrival": {
        "title": "Rain on Bellweather Lane",
        "body": "Julian slides a warm mug of {{item}} across the counter.",
        "choices": [
          { "label": "Hold his gaze", "next": "stacks", "effects": { "spark": 2 } },
          { "label": "Ask about the folio", "next": "folio", "requires": { "trust": 3 } }
        ]
      },
      "stacks": { "title": "Between the Stacks", "body": "…", "ending": true }
    }
  }
}
```

`start` is accepted as a legacy alias for `startScene`. `scenes`, `startScene` and
`initialState` may also be passed as top-level arguments instead of a `story` object.

**Output** — `valid`, `error_count`, `warning_count`, `errors[]`, `warnings[]`, `issues{}`,
`stats{}`.

| Issue code | Severity | Meaning |
| :--- | :--- | :--- |
| `SCHEMA_MISSING_SCENES`, `SCHEMA_MISSING_START`, `SCHEMA_START_NOT_FOUND` | error | graph is not runnable |
| `MISSING_TARGET` | error | a choice links to a scene that does not exist |
| `INVALID_GUARD` | error | `requires` is not an object of numbers |
| `SCHEMA_INVALID_SCENE`, `SCENE_INVALID_CHOICES`, `SCHEMA_CHOICE_NO_TARGET`, `SCHEMA_INVALID_EFFECTS`, `SCENE_INVALID_ENDING` | error | malformed scene or choice |
| `UNREACHABLE_SCENE` | warning | scene cannot be reached from `startScene` |
| `DEAD_END` | warning | non-ending scene with no choices |
| `LOOP_TRAP` | warning | reachable cycle with no exit to an ending |
| `INVALID_GUARD_UNKNOWN_KEY` | warning | guard reads a state key nothing declares or writes |
| `SCENE_MISSING_TITLE`, `SCENE_MISSING_BODY` | warning | incomplete authoring |

### 2. `step_story_state`

Run the deterministic reducer for one or more player choices.

**Input**

```json
{
  "story": { "…": "as above" },
  "choices": [0, "Open the folio"],
  "state": { "trust": 2 },
  "remember": ["My cat's name is Marmalade."]
}
```

`choices` entries may be integer indexes, case-insensitive labels, or `{index}` / `{label}`
objects. `state` overrides `initialState`; `memory` seeds a prior memory log.

**Output** — `final_scene`, `final_state`, `turns`, `history[]`, `steps[]` (each with
`guards_evaluated`, `fired_guards`, `unmet_guards`, `effects_applied`, `state`, `memory`),
`available_choices[]` for the scene the reader landed on, `stopped_reason`, and
`trace_hash` + `verification{}`.

**Effects.** Scalar numbers **add** (relationship meters are cumulative); strings, booleans,
arrays and nulls **assign**; explicit operators give full control:

```json
{
  "effects": {
    "trust": 2,
    "item": "amber ledger",
    "clues": { "op": "append", "value": "folio mentioned at the counter" },
    "curse": { "op": "delete" }
  }
}
```

**Guards.** A choice is visible only when every `requires` key is at least its minimum:

```json
{ "requires": { "trust": 3 } }
```

Unmet choices are filtered out of `available_choices` (never rendered as a greyed-out
option — that would leak the existence of the state variable), and a step that requests one
is recorded with `status: "guard_blocked"` and leaves state untouched.

**Determinism.** `trace_hash` is `sha256(canonical_json(payload))`, where
`canonical_json` means sorted keys, no whitespace, and integral floats written as integers.
Python and Node produce the *same* hash for the same inputs:

```json
{
  "verification": {
    "algorithm": "sha256",
    "canonicalization": "JSON with sorted keys, no whitespace, integral floats as integers",
    "hash": "2eeba186fb99…",
    "note": "Recompute sha256 over the canonical JSON of `payload`; a mismatch means the
             story state was mutated outside this reducer (silent state drift)."
  }
}
```

### 3. `query_ai_story_benchmark`

Query the verified **Nov 15, 2026 10-Platform Consumer AI Story Continuity Benchmark**
([doi:10.7910/DVN/YEBHQR](https://doi.org/10.7910/DVN/YEBHQR), CC-BY-4.0).

**Input**

```json
{ "platform": "Character.AI", "status": "fail" }
```

Both filters are optional and combinable. `platform` accepts names or aliases
(`"talkie"`, `"ai-dungeon"`, `"chai"`…); `status` accepts `pass`, `fail`,
`right_censored`, `untestable`, plus the aggregate `tested`.

**Output** — `benchmark{}` (protocol, summary, DOIs, explorer URL), `results[]`,
`count`, `filters{}`, `warnings[]`, and `citation{apa, bibtex, doi, license, explorer_url}`.

### 4. `detect_state_drift`

Check a transcript against a planted fact and classify the session with the five-mode
silent state drift taxonomy from
[*State Drift in Consumer LLM Interactive Fiction*](https://doi.org/10.5281/zenodo.24549412).

**Input**

```json
{
  "fact": { "key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2 },
  "transcript": [
    "It is raining again.",
    "My cat's name is Marmalade.",
    "Of course. Marmalade hates the rain.",
    "What is my cat's name?"
  ],
  "probe_turn": 4,
  "min_gap": 2
}
```

`transcript` entries may be plain strings or `{turn, speaker, text}` objects.
`fact.wrong_values[]` supplies contradiction candidates; `fact.aliases[]` supplies accepted
spellings; `fact.contradiction_mode` may be `wrong_values` (default) or
`key_mention_without_value`.

**Verdicts**

| Verdict | Mode | `passed` | Meaning |
| :--- | :--- | :--- | :--- |
| `PASS` | F0 | `true` | recalled at or after the probe, no contradiction |
| `F4_TRANSIENT_DEGRADATION` | F4 | `true` | stalled (empty turn, missing turn, repeated reply) then recovered |
| `F1_CONTRADICTION` | F1 | `false` | a later turn asserts a different value |
| `F1_OMISSION` | F1 | `false` | probe reached, fact never recalled |
| `F2_SESSION_NON_PERSISTENCE` | F2 | `false` | empty assistant turns after planting |
| `F3_GATING_CENSORING` | F3 | `null` | transcript stops before the probe — unknown, not failed |
| `F5_PLATFORM_DELISTING` | F5 | `null` | delisting prevented the session (`delisted: true`) |
| `FACT_NOT_PLANTED` | — | `null` | expected value never appears in the transcript |
| `EMPTY_TRANSCRIPT` | — | `null` | no turns supplied |

Output includes `per_turn[]` (`at_or_before_planting` / `recalled` / `contradicted` /
`omitted` / `empty`), `evidence{recall_turns, contradiction_turns, empty_turns,
stall_detected, probe_reached}`, the full `taxonomy[]` and the taxonomy citation.

---

## Resources

| URI | MIME type | Contents |
| :--- | :--- | :--- |
| `ouba://benchmark/2026-10-platform-matrix` | `application/json` | Full CC-BY-4.0 matrix for all 10 platforms, plus `citation{}` and `benchmark{}` metadata |
| `ouba://schema/story-graph-v1` | `application/schema+json` | Canonical JSON Schema (draft 2020-12) for `branching-story-kit` story graphs |

---

## The benchmark, in one table

Evaluation date `2026-11-15`. $0 spent, email-only identity, no CAPTCHA solving, no OAuth
linkage, no payment card, PG-13 content. Fact planted at turn 2, probed at turn 15.

| Platform | Category | Status | Turns | Turn-15 recall | TTFS (s) | Latency (s) | Signup gate | Mode |
| :--- | :--- | :--- | ---: | :--- | ---: | ---: | :---: | :---: |
| **Ouba** | Reader-first AI fiction | **PASS** | 20 | Pass (verbatim) | 15 | 7 | No | — |
| **Talkie** | Companion chatbot | **PASS** | 20 | Pass | 17 | 3 | No | — |
| **AI Dungeon** | Open sandbox | **PASS** | 7† | Pass (verbatim) | 70 | 8 | No | F4 |
| **Character.AI** | Companion chatbot | **FAIL** | 20 | Fail | 21 | 3 | Yes | **F1** |
| Janitor AI | Companion chatbot | right-censored | 0 | Not reached | 45 | — | Yes | F2 |
| Talefy | Reader-first AI fiction | right-censored | 0 | Not reached | 7 | — | Yes | F3 |
| Joyland | Companion chatbot | right-censored | 0 | Not reached | — | — | Yes | F3 |
| NovelAI | AI writing tool | right-censored | 0 | Not reached | — | — | Yes | F3 |
| Chai | Companion chatbot | untestable | — | Not tested | — | — | — | F5 |
| Galatea | Pre-written serial | untestable | — | Not tested | — | — | Yes (paid) | F3 |

† A transient free-queue stall at turn 7, not a hard paywall — the session resumed and
passed the turn-15 probe verbatim.

**Derived measures:** 10 products evaluated · 4 reached the turn-15 probe · 3 recalled the
fact (30% unconditional, 75% conditional) · 4 right-censored · 2 untestable · median time to
first story 19 s (range 7–70 s) · mean reply latency 5.3 s · **0 ad interruptions** across
every completed turn · 3 products with no signup gate before reading.

The single failure is the instructive one: Character.AI sustained 20 turns at ~3 s/reply,
fully on-persona, and simply did not have the fact. Nothing in the product's observable
behaviour announced the loss — the operational definition of silent state drift, and the
reason it requires an external probe rather than a self-report.

**Explore the matrix:** <https://www.ouba.art/tools/benchmark-explorer>

---

## Identifiers & citation

| Artifact | Identifier |
| :--- | :--- |
| **This software** | [github.com/ouba-studio/branching-story-mcp](https://github.com/ouba-studio/branching-story-mcp) · [PyPI](https://pypi.org/project/branching-story-mcp/) · [JSR](https://jsr.io/@ouba-studio/branching-story-mcp) · npm `@ouba-studio/branching-story-mcp` |
| **Primary dataset (CC-BY-4.0)** | [doi:10.7910/DVN/YEBHQR](https://doi.org/10.7910/DVN/YEBHQR) — Harvard Dataverse |
| **Preprint (Zenodo)** | [doi:10.5281/zenodo.24549412](https://doi.org/10.5281/zenodo.24549412) |
| **Preprint (Figshare)** | [doi:10.6084/m9.figshare.35126743](https://doi.org/10.6084/m9.figshare.35126743) |
| **Preprint (SSRN)** | [doi:10.17613/rmr3y-hgk56](https://doi.org/10.17613/rmr3y-hgk56) |
| **Core engine** | [branching-story-kit](https://github.com/ouba-studio/branching-story-kit) · [PyPI](https://pypi.org/project/branching-story-kit/) · [JSR](https://jsr.io/@ouba-studio/branching-story-kit) |
| **Benchmark explorer** | <https://www.ouba.art/tools/benchmark-explorer> |
| **Wikidata** | [Q140090475](https://www.wikidata.org/wiki/Q140090475) |

**APA 7**

> Ouba Studio. (2026). *Interactive Fiction & AI Story Apps Benchmark Dataset (2026)*
> [Data set]. Harvard Dataverse. https://doi.org/10.7910/DVN/YEBHQR

**BibTeX**

```bibtex
@dataset{ouba_studio_2026_ai_story_benchmark,
  author    = {{Ouba Studio}},
  title     = {Interactive Fiction \& AI Story Apps Benchmark Dataset (2026)},
  year      = {2026},
  publisher = {Harvard Dataverse},
  doi       = {10.7910/DVN/YEBHQR},
  url       = {https://doi.org/10.7910/DVN/YEBHQR},
  license   = {CC-BY-4.0},
  note      = {10-platform consumer AI story continuity benchmark; evaluation date 2026-11-15}
}

@software{ouba_studio_2026_branching_story_mcp,
  author  = {{Ouba Studio}},
  title   = {branching-story-mcp: A zero-dependency Model Context Protocol server for
             deterministic story state and the 2026 Consumer AI Story Continuity Benchmark},
  year    = {2026},
  version = {1.0.0},
  license = {MIT},
  url     = {https://github.com/ouba-studio/branching-story-mcp}
}
```

---

## Repository layout

```text
branching-story-mcp/
├── branching_story_mcp/          # Python package (stdlib only, >=3.10)
│   ├── __init__.py
│   ├── kernel.py                 # validator, reducer, drift detector, JSON schema
│   ├── benchmark_data.py         # verified CC-BY-4.0 matrix + citation builders
│   └── server.py                 # JSON-RPC 2.0 over stdio
├── js/                           # behaviour-identical ESM mirror (>=18)
│   ├── server.mjs
│   ├── kernel.mjs
│   ├── benchmark.mjs
│   └── index.d.ts
├── schema/story-graph-v1.schema.json
├── data/benchmark-2026-10-platform-matrix.json
├── examples/midnight-bookshop.json
├── tests/test_mcp_server.py      # real stdio handshake + all tools/resources
├── tests/test_js_server.mjs      # same suite against the Node build
├── server.json                   # official MCP Registry manifest
├── smithery.yaml · glama.json · jsr.json · package.json · pyproject.toml
└── LICENSE · CITATION.cff · CHANGELOG.md
```

## Development

```bash
# Python
pip install -e . && python -m unittest discover -s tests -v
python -m build                      # wheel + sdist into dist/

# Node
npm test                             # node --test tests/test_js_server.mjs
node js/server.mjs                   # then paste JSON-RPC lines
```

Both suites drive a **real child process** over stdio: `initialize` →
`notifications/initialized` → `tools/list` → all four `tools/call` → `resources/list` →
`resources/read` → `ping`, plus the error paths.

## License

[MIT](LICENSE) © 2026 Ouba Studio. The bundled benchmark data
(`benchmark_data.py`, `js/benchmark.mjs`, `data/benchmark-2026-10-platform-matrix.json` and
the `ouba://benchmark/2026-10-platform-matrix` resource) is
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/), Ouba Studio (2026),
[doi:10.7910/DVN/YEBHQR](https://doi.org/10.7910/DVN/YEBHQR).

---

**Ouba** — free reader-first interactive fiction on [web, iOS and Android](https://www.ouba.art/) ·
[2026 AI Story Apps Benchmark](https://www.ouba.art/i-tested-ai-story-apps) ·
[Benchmark Explorer](https://www.ouba.art/tools/benchmark-explorer) ·
[branching-story-kit](https://github.com/ouba-studio/branching-story-kit) ·
team@ouba.art
