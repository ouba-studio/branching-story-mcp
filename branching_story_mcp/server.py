"""Zero-dependency MCP server over stdio (JSON-RPC 2.0).

Implements Model Context Protocol ``2024-11-05`` and ``2025-03-26``:
``initialize``, ``notifications/initialized``, ``ping``, ``tools/list``,
``tools/call``, ``resources/list``, ``resources/read``.

Run it directly (``python -m branching_story_mcp.server``), through the console
script (``branching-story-mcp``), with ``uvx branching-story-mcp``, or with
``pipx run branching-story-mcp``. No third-party runtime dependencies.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .benchmark_data import BENCHMARK, EXPLORER_URL, benchmark_citation, query_benchmark
from .kernel import (
    SERVER_NAME,
    STORY_GRAPH_SCHEMA,
    VERSION,
    detect_state_drift,
    normalize_story,
    step_story_state,
    validate_story_graph,
)

__all__ = ["main", "handle_message", "TOOLS", "RESOURCES", "SERVER_INFO"]

SERVER_INFO = {"name": SERVER_NAME, "version": VERSION}

SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26")
DEFAULT_PROTOCOL_VERSION = "2025-03-26"

INSTRUCTIONS = (
    "branching-story-mcp exposes Ouba Studio's deterministic branching-story-kit "
    "story-state kernel and the CC-BY-4.0 2026 Consumer AI Story Continuity "
    "Benchmark (doi:10.7910/DVN/YEBHQR). Use validate_story_graph before stepping, "
    "step_story_state for zero-drift state transitions, query_ai_story_benchmark for "
    "verified per-platform continuity results, and detect_state_drift to classify a "
    "transcript against the five-mode silent state drift taxonomy. "
    f"Interactive explorer: {EXPLORER_URL}"
)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_STORY_PROPERTY: dict[str, Any] = {
    "type": "object",
    "description": (
        "A branching-story-kit v1 story graph: {id?, title?, startScene (or legacy start), "
        "initialState?, scenes}. Scenes map id -> {title, body, ending?, choices?}. "
        "Choices carry label, next (or href), optional requires {key: minimum} and optional "
        "effects {key: value | {op: set|add|append|delete, value}}."
    ),
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "validate_story_graph",
        "title": "Validate a branching story graph",
        "description": (
            "Validate a branching-story-kit JSON scene graph. Checks the schema, detects "
            "missing choice targets, unreachable scenes, dead-end loops and invalid guard "
            "predicates, and returns structured diagnostics with issue codes, stats and a "
            "pass/fail verdict."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "story": _STORY_PROPERTY,
                "scenes": {"type": "object", "description": "Alternative to `story`: the scenes map."},
                "startScene": {"type": "string", "description": "Alternative to `story`: the start scene id."},
                "initialState": {"type": "object", "description": "Alternative to `story`: the initial state vector."},
            },
            "additionalProperties": True,
        },
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "step_story_state",
        "title": "Advance deterministic story state",
        "description": (
            "Run the deterministic story-state reducer for one or more player choices. "
            "Evaluates `requires` guards, applies `set` / `add` / `append` effects through a "
            "single write path, and returns the next scene, updated state, fired guards, "
            "available choices and a turn-stamped memory trace with a verifiable SHA-256 "
            "trace hash. Zero silent state drift."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "story": _STORY_PROPERTY,
                "choices": {
                    "type": "array",
                    "items": {"anyOf": [{"type": "integer"}, {"type": "string"}, {"type": "object"}]},
                    "description": (
                        "Ordered player choices. Each entry is an integer index into the current "
                        "scene's choices, a case-insensitive choice label, or {index}/{label}."
                    ),
                },
                "state": {"type": "object", "description": "Optional state overrides applied on top of initialState."},
                "memory": {
                    "type": "array",
                    "items": {"anyOf": [{"type": "string"}, {"type": "object"}]},
                    "description": "Optional prior memory log: strings or {turn, fact} objects.",
                },
                "remember": {
                    "type": "array",
                    "items": {"anyOf": [{"type": "string"}, {"type": "object"}]},
                    "description": "Facts to plant in the turn-stamped memory log before stepping.",
                },
                "startScene": {"type": "string", "description": "Optional override for the entry scene."},
            },
            "required": ["story", "choices"],
            "additionalProperties": True,
        },
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "query_ai_story_benchmark",
        "title": "Query the 2026 AI story continuity benchmark",
        "description": (
            "Query the verified Nov 15 2026 10-Platform Consumer AI Story Continuity Benchmark "
            "(doi:10.7910/DVN/YEBHQR): Ouba 20t verbatim PASS, Talkie 20t PASS, AI Dungeon 7t "
            "verbatim PASS, Character.AI 20t FAIL (silent state loss), Janitor AI / Talefy / "
            "Joyland / NovelAI right-censored, Chai / Galatea untestable. Optional `platform` "
            "or `status` filter. Returns structured JSON plus full APA/BibTeX citation and the "
            "interactive benchmark explorer URL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform name or alias, e.g. 'Character.AI', 'talkie', 'ai-dungeon'.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pass", "fail", "right_censored", "untestable", "tested"],
                    "description": "Optional outcome filter.",
                },
            },
            "additionalProperties": True,
        },
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "detect_state_drift",
        "title": "Detect silent state drift in a transcript",
        "description": (
            "Given a planted fact {key, expected_value, planted_turn} and a transcript of turns, "
            "check deterministic recall / contradiction / omission and classify the session "
            "against the five-mode silent state drift taxonomy (F1 silent state loss, F2 session "
            "non-persistence, F3 gating censoring, F4 transient service degradation, F5 platform "
            "delisting) from doi:10.5281/zenodo.24549412."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "State key, e.g. 'cat_name'."},
                        "expected_value": {"type": "string", "description": "The planted value, e.g. 'Marmalade'."},
                        "planted_turn": {"type": "integer", "description": "1-based turn where the fact was planted."},
                        "wrong_values": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Values that would contradict the planted fact.",
                        },
                        "aliases": {"type": "array", "items": {"type": "string"}, "description": "Accepted spellings of the expected value."},
                        "contradiction_mode": {
                            "type": "string",
                            "enum": ["wrong_values", "key_mention_without_value"],
                            "description": "How contradictions are detected (default: wrong_values).",
                        },
                    },
                    "required": ["key", "expected_value"],
                    "additionalProperties": True,
                },
                "transcript": {
                    "type": "array",
                    "items": {
                        "anyOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "turn": {"type": "integer"},
                                    "speaker": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                                "required": ["text"],
                            },
                        ]
                    },
                    "description": "Conversation turns, oldest first.",
                },
                "probe_turn": {"type": "integer", "description": "Turn at which recall is probed (default: last turn)."},
                "min_gap": {"type": "integer", "description": "Minimum turns after planting before a session counts as probed (default 2)."},
                "delisted": {"type": "boolean", "description": "Set true when the platform was delisted (forces F5)."},
            },
            "required": ["fact", "transcript"],
            "additionalProperties": True,
        },
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
]

RESOURCE_BENCHMARK_URI = "ouba://benchmark/2026-10-platform-matrix"
RESOURCE_SCHEMA_URI = "ouba://schema/story-graph-v1"

RESOURCES: list[dict[str, Any]] = [
    {
        "uri": RESOURCE_BENCHMARK_URI,
        "name": "2026-10-platform-matrix",
        "title": "2026 Consumer AI Story Continuity Benchmark — 10-platform matrix",
        "description": (
            "Full CC-BY-4.0 per-platform matrix (evaluation date 2026-11-15, "
            "doi:10.7910/DVN/YEBHQR): status, turns completed, turn-15 recall, TTFS, latency, "
            "ads, signup gate, failure mode and notes for all 10 platforms."
        ),
        "mimeType": "application/json",
    },
    {
        "uri": RESOURCE_SCHEMA_URI,
        "name": "story-graph-v1",
        "title": "branching-story-kit story graph v1 JSON Schema",
        "description": "Canonical JSON Schema for branching-story-kit scene graphs (scenes, startScene, initialState).",
        "mimeType": "application/schema+json",
    },
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolError(Exception):
    """Raised for semantic tool failures; reported as isError to the client."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidParams(Exception):
    """Raised for malformed tool arguments; reported as JSON-RPC -32602."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Argument helpers
# ---------------------------------------------------------------------------


def _require_object(args: Any) -> dict[str, Any]:
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise InvalidParams("tool arguments must be a JSON object")
    return args


def _coerce_story(args: dict[str, Any]) -> dict[str, Any]:
    if isinstance(args.get("story"), dict):
        return args["story"]
    if isinstance(args.get("scenes"), dict):
        return {
            "id": args.get("id"),
            "title": args.get("title"),
            "startScene": args.get("startScene") or args.get("start"),
            "initialState": args.get("initialState") or {},
            "scenes": args["scenes"],
        }
    raise InvalidParams(
        "provide a `story` object (or the `scenes`, `startScene` and `initialState` fields)"
    )


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def tool_validate_story_graph(args: dict[str, Any]) -> dict[str, Any]:
    story = _coerce_story(args)
    return validate_story_graph(story)


def tool_step_story_state(args: dict[str, Any]) -> dict[str, Any]:
    story = _coerce_story(args)
    choices = args.get("choices")
    if choices is None:
        raise InvalidParams("`choices` is required: an array of choice indexes or labels")
    if not isinstance(choices, list):
        raise InvalidParams("`choices` must be an array")
    state = args.get("state")
    if state is not None and not isinstance(state, dict):
        raise InvalidParams("`state` must be an object")
    return step_story_state(
        story,
        choices,
        state=state,
        memory=args.get("memory"),
        remember=args.get("remember"),
        start_scene=args.get("startScene"),
    )


def tool_query_ai_story_benchmark(args: dict[str, Any]) -> dict[str, Any]:
    platform = args.get("platform")
    status = args.get("status")
    if platform is not None and not isinstance(platform, str):
        raise InvalidParams("`platform` must be a string")
    if status is not None and not isinstance(status, str):
        raise InvalidParams("`status` must be a string")
    return query_benchmark(platform=platform, status=status)


def tool_detect_state_drift(args: dict[str, Any]) -> dict[str, Any]:
    fact = args.get("fact")
    transcript = args.get("transcript")
    if fact is None:
        raise InvalidParams("`fact` is required: {key, expected_value, planted_turn?}")
    if transcript is None:
        raise InvalidParams("`transcript` is required: an array of turns")
    probe_turn = args.get("probe_turn")
    if probe_turn is not None and not isinstance(probe_turn, int):
        raise InvalidParams("`probe_turn` must be an integer")
    min_gap = args.get("min_gap", 2)
    if not isinstance(min_gap, int) or min_gap < 1:
        raise InvalidParams("`min_gap` must be a positive integer")
    delisted = args.get("delisted", False)
    if not isinstance(delisted, bool):
        raise InvalidParams("`delisted` must be a boolean")
    return detect_state_drift(
        fact,
        transcript,
        probe_turn=probe_turn,
        min_gap=min_gap,
        delisted=delisted,
    )


TOOL_HANDLERS = {
    "validate_story_graph": tool_validate_story_graph,
    "step_story_state": tool_step_story_state,
    "query_ai_story_benchmark": tool_query_ai_story_benchmark,
    "detect_state_drift": tool_detect_state_drift,
}


# ---------------------------------------------------------------------------
# Resource handlers
# ---------------------------------------------------------------------------


def read_resource(uri: str) -> dict[str, Any]:
    if uri == RESOURCE_BENCHMARK_URI:
        payload = {
            "license": BENCHMARK["license"],
            "license_url": BENCHMARK["license_url"],
            "dataset_doi": BENCHMARK["dataset_doi"],
            "dataset_url": BENCHMARK["dataset_url"],
            "explorer_url": EXPLORER_URL,
            "citation": benchmark_citation(),
            "benchmark": BENCHMARK,
        }
        mime = "application/json"
    elif uri == RESOURCE_SCHEMA_URI:
        payload = STORY_GRAPH_SCHEMA
        mime = "application/schema+json"
    else:
        raise ToolError(f"unknown resource URI: {uri}")
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": mime,
                "text": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            }
        ]
    }


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _tool_content(payload: dict[str, Any], is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": is_error,
    }


def handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    requested = params.get("protocolVersion") if isinstance(params, dict) else None
    protocol = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
    return {
        "protocolVersion": protocol,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
        },
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


def handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise InvalidParams("tools/call params must be an object")
    name = params.get("name")
    if not isinstance(name, str):
        raise InvalidParams("tools/call requires a string `name`")
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise InvalidParams(
            f"unknown tool {name!r}; available tools: " + ", ".join(sorted(TOOL_HANDLERS))
        )
    args = _require_object(params.get("arguments"))
    try:
        payload = handler(args)
    except ToolError as exc:
        return _tool_content({"ok": False, "error": exc.message, **exc.details}, is_error=True)
    except ValueError as exc:
        return _tool_content({"ok": False, "error": str(exc)}, is_error=True)
    return _tool_content(payload)


def handle_message(message: Any) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Returns a response dict or None (notifications)."""
    if isinstance(message, list):
        responses = [handle_message(item) for item in message]
        batch = [r for r in responses if r is not None]
        return batch or None

    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request: message must be an object")

    method = message.get("method")
    request_id = message.get("id")
    is_notification = "id" not in message

    if not isinstance(method, str):
        if is_notification:
            return None
        return _error(request_id, -32600, "Invalid Request: missing method")

    params = message.get("params")
    if params is None:
        params = {}

    # Notifications never receive a response.
    if is_notification:
        return None

    if method == "initialize":
        return _result(request_id, handle_initialize(params))
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "resources/list":
        return _result(request_id, {"resources": RESOURCES})
    if method == "resources/templates/list":
        return _result(request_id, {"resourceTemplates": []})
    if method == "prompts/list":
        return _result(request_id, {"prompts": []})
    if method == "tools/call":
        try:
            return _result(request_id, handle_tools_call(params))
        except InvalidParams as exc:
            return _error(request_id, -32602, exc.message)
    if method == "resources/read":
        if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
            return _error(request_id, -32602, "resources/read requires a string `uri`")
        try:
            return _result(request_id, read_resource(params["uri"]))
        except ToolError as exc:
            return _error(request_id, -32002, exc.message)
    if method == "logging/setLevel":
        return _result(request_id, {})
    return _error(request_id, -32601, f"Method not found: {method}")


def _emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    """Blocking stdio loop. Returns a process exit code."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _emit(_error(None, -32700, f"Parse error: {exc}"))
            continue
        response = handle_message(message)
        if response is not None:
            _emit(response)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
