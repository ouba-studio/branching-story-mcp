"""End-to-end tests for branching-story-mcp over real stdio JSON-RPC.

Every test spawns the actual server process and speaks MCP to it:
``initialize`` -> ``notifications/initialized`` -> ``tools/list`` -> all four
``tools/call`` -> ``resources/list`` -> ``resources/read`` -> ``ping``.

Run with either:
    python -m unittest discover -s tests -v
    pytest tests -q
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from branching_story_mcp.benchmark_data import BENCHMARK, query_benchmark  # noqa: E402
from branching_story_mcp.kernel import (  # noqa: E402
    DRIFT_TAXONOMY,
    canonical_json,
    detect_state_drift,
    sha256_hex,
    step_story_state,
    validate_story_graph,
)

EXAMPLE = json.loads((REPO_ROOT / "examples" / "midnight-bookshop.json").read_text(encoding="utf-8"))

# Pinned trace hash for examples/midnight-bookshop.json with choices [0, 0].
# Verified identical in the Python and the Node/ESM implementations.
PINNED_TRACE_HASH = "7d8d59e0191de2deb9003f2c854d18329967d921492a27c8f393d3ccd2c6a5c1"


class McpClient:
    """Minimal newline-delimited JSON-RPC client for a stdio MCP server."""

    def __init__(self, command: list[str], cwd: Path) -> None:
        self.process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

    def send(self, message: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def send_raw(self, line: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def receive(self) -> dict:
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise AssertionError(f"server closed stdout unexpectedly. stderr: {stderr}")
        return json.loads(line)

    def request(self, request_id: int, method: str, params: dict | None = None) -> dict:
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        return self.receive()

    def notify(self, method: str, params: dict | None = None) -> None:
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def call_tool(self, request_id: int, name: str, arguments: dict | None = None) -> dict:
        response = self.request(request_id, "tools/call", {"name": name, "arguments": arguments or {}})
        return response

    def read_resource(self, request_id: int, uri: str) -> dict:
        return self.request(request_id, "resources/read", {"uri": uri})

    def close(self) -> None:
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        for stream in (self.process.stdout, self.process.stderr):
            if stream:
                stream.close()


class _ServerTestBase(unittest.TestCase):
    """Base class that gives every test a fresh server process."""

    command: list[str] = [sys.executable, "-m", "branching_story_mcp.server"]

    def setUp(self) -> None:
        self.client = McpClient(self.command, REPO_ROOT)
        self.addCleanup(self.client.close)

    def initialize(self, protocol: str = "2025-03-26") -> dict:
        response = self.client.request(
            1,
            "initialize",
            {
                "protocolVersion": protocol,
                "capabilities": {},
                "clientInfo": {"name": "branching-story-mcp-tests", "version": "1.0.0"},
            },
        )
        self.client.notify("notifications/initialized")
        return response


class TestHandshake(_ServerTestBase):
    def test_initialize_2025_03_26(self):
        response = self.initialize("2025-03-26")
        self.assertNotIn("error", response)
        result = response["result"]
        self.assertEqual(result["protocolVersion"], "2025-03-26")
        self.assertEqual(result["serverInfo"], {"name": "branching-story-mcp", "version": "1.0.0"})
        self.assertEqual(result["capabilities"]["tools"], {"listChanged": False})
        self.assertEqual(
            result["capabilities"]["resources"],
            {"subscribe": False, "listChanged": False},
        )
        self.assertIn("instructions", result)

    def test_initialize_echoes_2024_11_05(self):
        response = self.initialize("2024-11-05")
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")

    def test_initialize_falls_back_for_unsupported_protocol(self):
        response = self.initialize("1999-01-01")
        self.assertEqual(response["result"]["protocolVersion"], "2025-03-26")

    def test_initialized_notification_gets_no_response(self):
        self.initialize()
        self.client.notify("notifications/initialized")
        ping = self.client.request(2, "ping")
        self.assertEqual(ping["result"], {})
        self.assertEqual(ping["id"], 2)

    def test_ping_returns_empty_object(self):
        self.initialize()
        response = self.client.request(7, "ping")
        self.assertEqual(response["result"], {})

    def test_batch_request_returns_batch_response(self):
        self.initialize()
        self.client.send(
            [
                {"jsonrpc": "2.0", "id": 10, "method": "ping"},
                {"jsonrpc": "2.0", "id": 11, "method": "tools/list"},
            ]
        )
        batch = self.client.receive()
        self.assertIsInstance(batch, list)
        self.assertEqual([item["id"] for item in batch], [10, 11])
        self.assertEqual(batch[0]["result"], {})
        self.assertIn("tools", batch[1]["result"])

    def test_unknown_method_is_method_not_found(self):
        response = self.client.request(3, "resources/subscribe", {"uri": "ouba://schema/story-graph-v1"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_parse_error_is_reported(self):
        self.client.send_raw("{not json")
        response = self.client.receive()
        self.assertEqual(response["error"]["code"], -32700)

    def test_invalid_request_is_reported(self):
        self.client.send_raw('"a string"')
        response = self.client.receive()
        self.assertEqual(response["error"]["code"], -32600)

    def test_notification_with_missing_method_is_ignored(self):
        self.client.send_raw('{"jsonrpc":"2.0"}')
        ping = self.client.request(4, "ping")
        self.assertEqual(ping["result"], {})


class TestToolsList(_ServerTestBase):
    def test_four_tools_with_json_schemas(self):
        self.initialize()
        response = self.client.request(2, "tools/list")
        tools = response["result"]["tools"]
        self.assertEqual(
            [tool["name"] for tool in tools],
            ["validate_story_graph", "step_story_state", "query_ai_story_benchmark", "detect_state_drift"],
        )
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertEqual(tool["outputSchema"]["type"], "object")
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])
            self.assertTrue(tool["title"])

    def test_step_story_state_requires_story_and_choices(self):
        self.initialize()
        schema = self.client.request(2, "tools/list")["result"]["tools"][1]["inputSchema"]
        self.assertEqual(sorted(schema["required"]), ["choices", "story"])

    def test_detect_state_drift_requires_fact_and_transcript(self):
        self.initialize()
        schema = self.client.request(2, "tools/list")["result"]["tools"][3]["inputSchema"]
        self.assertEqual(sorted(schema["required"]), ["fact", "transcript"])


class TestResources(_ServerTestBase):
    def test_resources_list_has_two_resources(self):
        self.initialize()
        response = self.client.request(2, "resources/list")
        resources = response["result"]["resources"]
        self.assertEqual(len(resources), 2)
        uris = {resource["uri"] for resource in resources}
        self.assertEqual(
            uris,
            {"ouba://benchmark/2026-10-platform-matrix", "ouba://schema/story-graph-v1"},
        )
        by_uri = {resource["uri"]: resource for resource in resources}
        self.assertEqual(by_uri["ouba://benchmark/2026-10-platform-matrix"]["mimeType"], "application/json")
        self.assertEqual(by_uri["ouba://schema/story-graph-v1"]["mimeType"], "application/schema+json")

    def test_read_benchmark_matrix(self):
        self.initialize()
        response = self.client.read_resource(3, "ouba://benchmark/2026-10-platform-matrix")
        contents = response["result"]["contents"]
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0]["uri"], "ouba://benchmark/2026-10-platform-matrix")
        self.assertEqual(contents[0]["mimeType"], "application/json")
        payload = json.loads(contents[0]["text"])
        self.assertEqual(payload["license"], "CC-BY-4.0")
        self.assertEqual(payload["dataset_doi"], "10.7910/DVN/YEBHQR")
        self.assertEqual(payload["benchmark"]["evaluation_date"], "2026-11-15")
        self.assertEqual(len(payload["benchmark"]["platforms"]), 10)
        self.assertIn("apa", payload["citation"])

    def test_read_story_graph_schema(self):
        self.initialize()
        response = self.client.read_resource(4, "ouba://schema/story-graph-v1")
        contents = response["result"]["contents"]
        self.assertEqual(contents[0]["mimeType"], "application/schema+json")
        schema = json.loads(contents[0]["text"])
        self.assertEqual(schema["$id"], "ouba://schema/story-graph-v1")
        self.assertEqual(schema["type"], "object")
        self.assertIn("scenes", schema["properties"])
        self.assertIn("startScene", schema["properties"])
        self.assertIn("requires", schema["$defs"]["choice"]["properties"])

    def test_read_unknown_resource_is_error(self):
        self.initialize()
        response = self.client.read_resource(5, "ouba://does-not/exist")
        self.assertEqual(response["error"]["code"], -32002)

    def test_resources_read_requires_uri(self):
        self.initialize()
        response = self.client.request(6, "resources/read", {})
        self.assertEqual(response["error"]["code"], -32602)

    def test_resource_templates_list_is_empty(self):
        self.initialize()
        response = self.client.request(7, "resources/templates/list")
        self.assertEqual(response["result"], {"resourceTemplates": []})


class TestValidateStoryGraph(_ServerTestBase):
    def test_valid_graph_passes(self):
        self.initialize()
        response = self.client.call_tool(2, "validate_story_graph", {"story": EXAMPLE})
        self.assertFalse(response["result"]["isError"])
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["error_count"], 0)
        self.assertEqual(payload["stats"]["scenes"], 4)
        self.assertEqual(payload["stats"]["endings"], 2)
        self.assertEqual(payload["stats"]["unreachable_scenes"], 0)
        text = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(text["valid"], True)

    def test_missing_target_is_an_error(self):
        self.initialize()
        story = {
            "startScene": "a",
            "scenes": {"a": {"title": "A", "body": "b", "choices": [{"label": "Go", "next": "ghost"}]}},
        }
        response = self.client.call_tool(2, "validate_story_graph", {"story": story})
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["valid"])
        codes = {error["code"] for error in payload["errors"]}
        self.assertIn("MISSING_TARGET", codes)
        self.assertEqual(payload["issues"]["missing_targets"][0]["next"], "ghost")

    def test_unreachable_scene_dead_end_and_loop_trap(self):
        self.initialize()
        story = {
            "startScene": "a",
            "scenes": {
                "a": {"title": "A", "body": "b", "choices": [{"label": "Loop", "next": "b"}]},
                "b": {"title": "B", "body": "c", "choices": [{"label": "Back", "next": "a"}]},
                "island": {"title": "Island", "body": "d", "ending": True},
            },
        }
        response = self.client.call_tool(2, "validate_story_graph", {"story": story})
        payload = response["result"]["structuredContent"]
        codes = {warning["code"] for warning in payload["warnings"]}
        self.assertIn("UNREACHABLE_SCENE", codes)
        self.assertIn("LOOP_TRAP", codes)
        self.assertEqual(payload["issues"]["unreachable_scenes"], [{"scene": "island"}])
        self.assertEqual(payload["issues"]["loop_traps"], [{"scene": "a"}, {"scene": "b"}])

    def test_dead_end_scene_is_flagged(self):
        self.initialize()
        story = {
            "startScene": "a",
            "scenes": {
                "a": {"title": "A", "body": "b", "choices": [{"label": "Go", "next": "b"}]},
                "b": {"title": "B", "body": "c"},
            },
        }
        response = self.client.call_tool(2, "validate_story_graph", {"story": story})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["issues"]["dead_ends"], [{"scene": "b"}])

    def test_invalid_guard_predicates(self):
        self.initialize()
        story = {
            "startScene": "a",
            "initialState": {"trust": 1},
            "scenes": {
                "a": {
                    "title": "A",
                    "body": "b",
                    "choices": [
                        {"label": "Bad", "next": "a", "requires": {"trust": "high"}},
                        {"label": "Unknown", "next": "a", "requires": {"charisma": 2}},
                    ],
                }
            },
        }
        response = self.client.call_tool(2, "validate_story_graph", {"story": story})
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["valid"])
        codes = {error["code"] for error in payload["errors"]}
        self.assertIn("INVALID_GUARD", codes)
        warning_codes = {warning["code"] for warning in payload["warnings"]}
        self.assertIn("INVALID_GUARD_UNKNOWN_KEY", warning_codes)

    def test_missing_scenes(self):
        self.initialize()
        response = self.client.call_tool(2, "validate_story_graph", {"story": {"startScene": "a"}})
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["errors"][0]["code"], "SCHEMA_MISSING_SCENES")

    def test_top_level_fields_instead_of_story_object(self):
        self.initialize()
        response = self.client.call_tool(
            2,
            "validate_story_graph",
            {
                "scenes": EXAMPLE["scenes"],
                "startScene": EXAMPLE["startScene"],
                "initialState": EXAMPLE["initialState"],
            },
        )
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["valid"])

    def test_missing_story_argument_is_invalid_params(self):
        self.initialize()
        response = self.client.request(2, "tools/call", {"name": "validate_story_graph", "arguments": {}})
        self.assertEqual(response["error"]["code"], -32602)


class TestStepStoryState(_ServerTestBase):
    def test_effects_and_next_scene(self):
        self.initialize()
        response = self.client.call_tool(2, "step_story_state", {"story": EXAMPLE, "choices": [0]})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["final_scene"], "stacks")
        self.assertEqual(payload["final_state"]["spark"], 3)
        self.assertEqual(payload["turns"], 1)
        self.assertEqual(payload["history"], ["arrival", "stacks"])
        self.assertEqual(payload["stopped_reason"], "choices_exhausted")

    def test_guard_blocks_and_leaves_state_untouched(self):
        self.initialize()
        response = self.client.call_tool(2, "step_story_state", {"story": EXAMPLE, "choices": [1]})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["steps"][0]["status"], "guard_blocked")
        self.assertEqual(payload["stopped_reason"], "guard_blocked")
        self.assertEqual(payload["final_scene"], "arrival")
        self.assertEqual(payload["final_state"]["trust"], 1)
        self.assertEqual(payload["steps"][0]["unmet_guards"][0]["key"], "trust")

    def test_set_add_append_ops(self):
        self.initialize()
        response = self.client.call_tool(2, "step_story_state", {"story": EXAMPLE, "choices": [0, 0]})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["final_scene"], "folio")
        self.assertEqual(payload["final_state"]["spark"], 3)
        self.assertEqual(payload["final_state"]["trust"], 3)
        self.assertEqual(payload["stopped_reason"], "ending_reached")

    def test_explicit_append_operator(self):
        self.initialize()
        story = {
            "startScene": "a",
            "initialState": {"clues": []},
            "scenes": {
                "a": {
                    "title": "A",
                    "body": "b",
                    "choices": [
                        {"label": "Note", "next": "b", "effects": {"clues": {"op": "append", "value": "x"}}}
                    ],
                },
                "b": {"title": "B", "body": "c", "ending": True},
            },
        }
        response = self.client.call_tool(2, "step_story_state", {"story": story, "choices": [0]})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["final_state"]["clues"], ["x"])
        self.assertEqual(payload["steps"][0]["effects_applied"][0]["op"], "append")

    def test_memory_trace_is_turn_stamped(self):
        self.initialize()
        response = self.client.call_tool(
            2,
            "step_story_state",
            {
                "story": EXAMPLE,
                "choices": [0],
                "memory": [{"turn": 0, "fact": "reader prefers tea"}],
                "remember": ["My cat's name is Marmalade."],
            },
        )
        payload = response["result"]["structuredContent"]
        self.assertEqual(len(payload["memory_trace"]), 2)
        self.assertEqual(payload["memory_trace"][0], {"turn": 0, "fact": "reader prefers tea"})
        self.assertEqual(payload["memory_trace"][1], {"turn": 0, "fact": "My cat's name is Marmalade."})
        self.assertEqual(payload["steps"][0]["memory"], payload["memory_trace"])

    def test_trace_hash_is_deterministic_and_pinned(self):
        self.initialize()
        first = self.client.call_tool(2, "step_story_state", {"story": EXAMPLE, "choices": [0, 0]})
        second = self.client.call_tool(3, "step_story_state", {"story": EXAMPLE, "choices": [0, 0]})
        hash_one = first["result"]["structuredContent"]["trace_hash"]
        hash_two = second["result"]["structuredContent"]["trace_hash"]
        self.assertEqual(hash_one, hash_two)
        self.assertEqual(hash_one, PINNED_TRACE_HASH)
        other = self.client.call_tool(4, "step_story_state", {"story": EXAMPLE, "choices": [2]})
        self.assertNotEqual(other["result"]["structuredContent"]["trace_hash"], hash_one)

    def test_trace_hash_can_be_recomputed_from_payload(self):
        self.initialize()
        response = self.client.call_tool(2, "step_story_state", {"story": EXAMPLE, "choices": [0, 0]})
        payload = response["result"]["structuredContent"]
        recomputed = sha256_hex(canonical_json(payload["verification"]["payload"]))
        self.assertEqual(recomputed, payload["trace_hash"])
        self.assertEqual(payload["verification"]["algorithm"], "sha256")

    def test_choices_by_label(self):
        self.initialize()
        response = self.client.call_tool(
            2, "step_story_state", {"story": EXAMPLE, "choices": ["hold his gaze"]}
        )
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["final_scene"], "stacks")

    def test_available_choices_reflect_guards(self):
        self.initialize()
        blocked = self.client.call_tool(
            2, "step_story_state", {"story": EXAMPLE, "choices": [], "state": {"trust": 1}}
        )["result"]["structuredContent"]
        by_index = {choice["choice_index"]: choice for choice in blocked["available_choices"]}
        self.assertTrue(by_index[0]["available"])
        self.assertFalse(by_index[1]["available"])
        self.assertEqual(by_index[1]["unmet"][0]["key"], "trust")
        self.assertTrue(by_index[2]["available"])

        unlocked = self.client.call_tool(
            3, "step_story_state", {"story": EXAMPLE, "choices": [], "state": {"trust": 5}}
        )["result"]["structuredContent"]
        self.assertTrue(all(choice["available"] for choice in unlocked["available_choices"]))

    def test_unknown_choice_index_is_tool_error(self):
        self.initialize()
        response = self.client.call_tool(2, "step_story_state", {"story": EXAMPLE, "choices": [99]})
        self.assertTrue(response["result"]["isError"])
        self.assertIn("out of range", response["result"]["structuredContent"]["error"])

    def test_missing_choices_is_invalid_params(self):
        self.initialize()
        response = self.client.request(2, "tools/call", {"name": "step_story_state", "arguments": {"story": EXAMPLE}})
        self.assertEqual(response["error"]["code"], -32602)


class TestQueryBenchmark(_ServerTestBase):
    def test_unfiltered_returns_all_ten_platforms(self):
        self.initialize()
        response = self.client.call_tool(2, "query_ai_story_benchmark", {})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["count"], 10)
        self.assertEqual(len(payload["results"]), 10)
        self.assertEqual(payload["benchmark"]["dataset_doi"], "10.7910/DVN/YEBHQR")
        self.assertEqual(payload["benchmark"]["summary"]["probe_administered"], 4)

    def test_platform_filter_character_ai(self):
        self.initialize()
        response = self.client.call_tool(2, "query_ai_story_benchmark", {"platform": "Character.AI"})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["count"], 1)
        result = payload["results"][0]
        self.assertEqual(result["platform"], "Character.AI")
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failure_mode"], "F1")
        self.assertEqual(result["turns_completed"], 20)

    def test_platform_alias(self):
        self.initialize()
        response = self.client.call_tool(2, "query_ai_story_benchmark", {"platform": "aidungeon"})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["results"][0]["platform"], "AI Dungeon")
        self.assertEqual(payload["results"][0]["turns_completed"], 7)

    def test_status_filter_pass(self):
        self.initialize()
        response = self.client.call_tool(2, "query_ai_story_benchmark", {"status": "pass"})
        payload = response["result"]["structuredContent"]
        self.assertEqual([p["platform"] for p in payload["results"]], ["Ouba", "Talkie", "AI Dungeon"])

    def test_status_filter_right_censored(self):
        self.initialize()
        response = self.client.call_tool(2, "query_ai_story_benchmark", {"status": "right_censored"})
        payload = response["result"]["structuredContent"]
        self.assertEqual(
            [p["platform"] for p in payload["results"]],
            ["Janitor AI", "Talefy", "Joyland", "NovelAI"],
        )

    def test_status_filter_untestable(self):
        self.initialize()
        response = self.client.call_tool(2, "query_ai_story_benchmark", {"status": "untestable"})
        payload = response["result"]["structuredContent"]
        self.assertEqual([p["platform"] for p in payload["results"]], ["Chai", "Galatea"])

    def test_combined_filters(self):
        self.initialize()
        response = self.client.call_tool(
            2, "query_ai_story_benchmark", {"platform": "Ouba", "status": "pass"}
        )
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["turn15_probe"], "Pass (verbatim)")

    def test_unknown_platform_returns_warning_and_suggestions(self):
        self.initialize()
        response = self.client.call_tool(2, "query_ai_story_benchmark", {"platform": "Myspace"})
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["count"], 0)
        self.assertTrue(payload["warnings"])
        self.assertIn("known platforms", payload["warnings"][0])

    def test_citation_is_complete(self):
        self.initialize()
        response = self.client.call_tool(2, "query_ai_story_benchmark", {})
        citation = response["result"]["structuredContent"]["citation"]
        self.assertIn("Ouba Studio. (2026)", citation["apa"])
        self.assertIn("10.7910/DVN/YEBHQR", citation["apa"])
        self.assertIn("@dataset{", citation["bibtex"])
        self.assertEqual(citation["license"], "CC-BY-4.0")
        self.assertEqual(citation["explorer_url"], "https://www.ouba.art/tools/benchmark-explorer")

    def test_resource_and_tool_agree(self):
        self.initialize()
        tool = self.client.call_tool(2, "query_ai_story_benchmark", {})["result"]["structuredContent"]
        resource = self.client.read_resource(3, "ouba://benchmark/2026-10-platform-matrix")
        payload = json.loads(resource["result"]["contents"][0]["text"])
        self.assertEqual(tool["results"], payload["benchmark"]["platforms"])


class TestDetectStateDrift(_ServerTestBase):
    def _drift(self, request_id, fact, transcript, **extra):
        arguments = {"fact": fact, "transcript": transcript}
        arguments.update(extra)
        return self.client.call_tool(request_id, "detect_state_drift", arguments)["result"]["structuredContent"]

    def test_pass(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade.", "Lovely.", "And now?", "Marmalade, of course."],
            probe_turn=5,
        )
        self.assertEqual(payload["verdict"], "PASS")
        self.assertTrue(payload["passed"])
        self.assertFalse(payload["drift_detected"])
        self.assertEqual(payload["evidence"]["recall_turns"], [5])

    def test_omission_is_silent_state_loss(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade.", "Nice weather.", "Anyway.", "Who is your cat?"],
            probe_turn=5,
        )
        self.assertEqual(payload["verdict"], "F1_OMISSION")
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["mode"], "F1")

    def test_contradiction(self):
        self.initialize()
        payload = self._drift(
            2,
            {
                "key": "cat_name",
                "expected_value": "Marmalade",
                "planted_turn": 2,
                "wrong_values": ["Rex"],
            },
            ["Hello.", "My cat's name is Marmalade.", "Nice weather.", "Your cat is Rex.", "Right."],
            probe_turn=5,
        )
        self.assertEqual(payload["verdict"], "F1_CONTRADICTION")
        self.assertFalse(payload["passed"])
        self.assertEqual(payload["evidence"]["contradiction_turns"], [4])

    def test_transient_degradation(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade.", "Sure.", "", "Still there?", "Marmalade."],
            probe_turn=6,
        )
        self.assertEqual(payload["verdict"], "F4_TRANSIENT_DEGRADATION")
        self.assertTrue(payload["passed"])
        self.assertTrue(payload["evidence"]["stall_detected"])

    def test_right_censored(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade."],
        )
        self.assertEqual(payload["verdict"], "F3_GATING_CENSORING")
        self.assertIsNone(payload["passed"])
        self.assertFalse(payload["evidence"]["probe_reached"])

    def test_session_non_persistence(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade.", "", "", "Anyone?"],
            probe_turn=5,
        )
        self.assertEqual(payload["verdict"], "F2_SESSION_NON_PERSISTENCE")
        self.assertEqual(payload["evidence"]["empty_turns"], [3, 4])

    def test_fact_not_planted(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "Nice weather.", "Goodbye."],
        )
        self.assertEqual(payload["verdict"], "FACT_NOT_PLANTED")
        self.assertIsNone(payload["passed"])

    def test_delisted_forces_f5(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade."],
            delisted=True,
        )
        self.assertEqual(payload["verdict"], "F5_PLATFORM_DELISTING")
        self.assertEqual(payload["mode_code"], "F5")

    def test_taxonomy_has_five_modes(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade.", "Marmalade"],
        )
        codes = [mode["code"] for mode in payload["taxonomy"]]
        self.assertEqual(codes, ["F1", "F2", "F3", "F4", "F5"])
        self.assertEqual(payload["taxonomy_source"]["doi"], "10.5281/zenodo.24549412")

    def test_per_turn_relations(self):
        self.initialize()
        payload = self._drift(
            2,
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade.", "Nice weather.", "Marmalade"],
        )
        relations = [entry["relation"] for entry in payload["per_turn"]]
        self.assertEqual(relations, ["at_or_before_planting", "at_or_before_planting", "omitted", "recalled"])

    def test_empty_transcript(self):
        self.initialize()
        payload = self._drift(2, {"key": "cat_name", "expected_value": "Marmalade"}, [])
        self.assertEqual(payload["verdict"], "EMPTY_TRANSCRIPT")

    def test_missing_fact_is_invalid_params(self):
        self.initialize()
        response = self.client.request(2, "tools/call", {"name": "detect_state_drift", "arguments": {"transcript": []}})
        self.assertEqual(response["error"]["code"], -32602)


class TestToolErrors(_ServerTestBase):
    def test_unknown_tool_is_invalid_params(self):
        self.initialize()
        response = self.client.request(2, "tools/call", {"name": "nonexistent_tool", "arguments": {}})
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("unknown tool", response["error"]["message"])

    def test_unknown_tool_lists_available_tools(self):
        self.initialize()
        response = self.client.request(2, "tools/call", {"name": "nope", "arguments": {}})
        self.assertIn("step_story_state", response["error"]["message"])

    def test_malformed_arguments_is_invalid_params(self):
        self.initialize()
        response = self.client.request(2, "tools/call", {"name": "validate_story_graph", "arguments": "not-an-object"})
        self.assertEqual(response["error"]["code"], -32602)

    def test_broken_story_is_is_error_not_protocol_error(self):
        self.initialize()
        response = self.client.call_tool(2, "step_story_state", {"story": {"scenes": {}}, "choices": [0]})
        self.assertNotIn("error", response)
        self.assertTrue(response["result"]["isError"])


class TestKernelDirect(unittest.TestCase):
    """Direct kernel tests (no subprocess) for speed and precision."""

    def test_validate_example_is_valid(self):
        result = validate_story_graph(EXAMPLE)
        self.assertTrue(result["valid"])
        self.assertEqual(result["stats"]["scenes"], 4)
        self.assertEqual(result["stats"]["reachable_scenes"], 4)

    def test_canonical_json_sorts_keys_and_collapses_floats(self):
        self.assertEqual(canonical_json({"b": 1.0, "a": 2}), '{"a":2,"b":1}')
        self.assertEqual(canonical_json({"b": 1.5, "a": [2.0, 3]}), '{"a":[2,3],"b":1.5}')

    def test_sha256_of_canonical_payload_is_stable(self):
        payload = {"story_id": "demo", "steps": [{"turn": 1, "state": {"trust": 2.0}}]}
        self.assertEqual(sha256_hex(canonical_json(payload)), sha256_hex(canonical_json(payload)))

    def test_step_is_pure_across_calls(self):
        first = step_story_state(EXAMPLE, [0, 0])
        second = step_story_state(EXAMPLE, [0, 0])
        self.assertEqual(first["trace_hash"], second["trace_hash"])
        self.assertEqual(first["final_state"], second["final_state"])

    def test_benchmark_has_ten_platforms_and_four_probe_administered(self):
        self.assertEqual(len(BENCHMARK["platforms"]), 10)
        self.assertEqual(BENCHMARK["summary"]["probe_administered"], 4)
        statuses = [platform["status"] for platform in BENCHMARK["platforms"]]
        self.assertEqual(statuses.count("pass"), 3)
        self.assertEqual(statuses.count("fail"), 1)
        self.assertEqual(statuses.count("right_censored"), 4)
        self.assertEqual(statuses.count("untestable"), 2)

    def test_benchmark_query_matches_module(self):
        payload = query_benchmark(status="fail")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["platform"], "Character.AI")

    def test_drift_taxonomy_is_five_modes(self):
        self.assertEqual([mode["code"] for mode in DRIFT_TAXONOMY], ["F1", "F2", "F3", "F4", "F5"])

    def test_drift_detector_direct(self):
        result = detect_state_drift(
            {"key": "cat_name", "expected_value": "Marmalade", "planted_turn": 2},
            ["Hello.", "My cat's name is Marmalade.", "Marmalade"],
        )
        self.assertEqual(result["verdict"], "PASS")

    def test_effect_unknown_op_raises(self):
        story = {
            "startScene": "a",
            "scenes": {
                "a": {
                    "title": "A",
                    "body": "b",
                    "choices": [{"label": "Go", "next": "a", "effects": {"trust": {"op": "explode"}}}],
                }
            },
        }
        with self.assertRaises(ValueError):
            step_story_state(story, [0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
