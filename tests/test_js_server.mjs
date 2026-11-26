/**
 * tests/test_js_server.mjs — end-to-end MCP stdio tests for the Node/ESM build.
 *
 * Spawns `node js/server.mjs` and speaks real JSON-RPC 2.0 to it:
 * initialize -> notifications/initialized -> tools/list -> all four tools/call
 * -> resources/list -> resources/read -> ping, plus the error paths.
 *
 * Run: `npm test` or `node --test tests/test_js_server.mjs`
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(HERE, "..");
const EXAMPLE = JSON.parse(readFileSync(join(REPO_ROOT, "examples", "midnight-bookshop.json"), "utf8"));

// Pinned trace hash for examples/midnight-bookshop.json with choices [0, 0].
// Identical to the Python implementation's output.
const PINNED_TRACE_HASH = "7d8d59e0191de2deb9003f2c854d18329967d921492a27c8f393d3ccd2c6a5c1";

class McpClient {
  constructor() {
    this.child = spawn(process.execPath, [join(REPO_ROOT, "js", "server.mjs")], {
      cwd: REPO_ROOT,
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.buffer = "";
    this.waiters = [];
    this.exited = null;
    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk) => {
      this.buffer += chunk;
      let index;
      while ((index = this.buffer.indexOf("\n")) >= 0) {
        const line = this.buffer.slice(0, index).trim();
        this.buffer = this.buffer.slice(index + 1);
        if (!line) continue;
        const waiter = this.waiters.shift();
        if (waiter) waiter.resolve(JSON.parse(line));
      }
    });
    this.child.on("exit", (code, signal) => {
      this.exited = { code, signal };
      for (const waiter of this.waiters.splice(0)) {
        waiter.reject(new Error(`server exited (code=${code}, signal=${signal})`));
      }
    });
    this.stderr = "";
    this.child.stderr.setEncoding("utf8");
    this.child.stderr.on("data", (chunk) => {
      this.stderr += chunk;
    });
  }

  send(message) {
    this.child.stdin.write(`${JSON.stringify(message)}\n`);
  }

  sendRaw(line) {
    this.child.stdin.write(`${line}\n`);
  }

  receive() {
    return new Promise((resolve, reject) => {
      this.waiters.push({ resolve, reject });
    });
  }

  async request(id, method, params) {
    const message = { jsonrpc: "2.0", id, method };
    if (params !== undefined) message.params = params;
    this.send(message);
    return this.receive();
  }

  notify(method, params) {
    const message = { jsonrpc: "2.0", method };
    if (params !== undefined) message.params = params;
    this.send(message);
  }

  async callTool(id, name, args) {
    return this.request(id, "tools/call", { name, arguments: args || {} });
  }

  async initialize(protocol = "2025-03-26") {
    const response = await this.request(1, "initialize", {
      protocolVersion: protocol,
      capabilities: {},
      clientInfo: { name: "branching-story-mcp-tests", version: "1.0.0" },
    });
    this.notify("notifications/initialized");
    return response;
  }

  close() {
    return new Promise((resolve) => {
      if (this.exited) return resolve();
      this.child.stdin.end();
      const timer = setTimeout(() => {
        this.child.kill();
        resolve();
      }, 5000);
      this.child.on("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
  }
}

function withServer(fn) {
  return async () => {
    const client = new McpClient();
    try {
      await fn(client);
    } finally {
      await client.close();
    }
  };
}

// ---------------------------------------------------------------------------
// Handshake
// ---------------------------------------------------------------------------

test(
  "initialize negotiates 2025-03-26",
  withServer(async (client) => {
    const response = await client.initialize("2025-03-26");
    assert.equal(response.result.protocolVersion, "2025-03-26");
    assert.deepEqual(response.result.serverInfo, { name: "branching-story-mcp", version: "1.0.0" });
    assert.deepEqual(response.result.capabilities.tools, { listChanged: false });
    assert.deepEqual(response.result.capabilities.resources, { subscribe: false, listChanged: false });
    assert.ok(response.result.instructions.length > 50);
  })
);

test(
  "initialize echoes 2024-11-05 and falls back for unknown versions",
  withServer(async (client) => {
    const old = await client.request(2, "initialize", { protocolVersion: "2024-11-05" });
    assert.equal(old.result.protocolVersion, "2024-11-05");
    const unknown = await client.request(3, "initialize", { protocolVersion: "1999-01-01" });
    assert.equal(unknown.result.protocolVersion, "2025-03-26");
  })
);

test(
  "ping returns an empty object",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(2, "ping");
    assert.deepEqual(response.result, {});
  })
);

test(
  "notifications never get a response",
  withServer(async (client) => {
    await client.initialize();
    client.notify("notifications/initialized");
    const ping = await client.request(2, "ping");
    assert.equal(ping.id, 2);
  })
);

test(
  "batch requests return a batch response",
  withServer(async (client) => {
    await client.initialize();
    client.send([
      { jsonrpc: "2.0", id: 10, method: "ping" },
      { jsonrpc: "2.0", id: 11, method: "tools/list" },
    ]);
    const batch = await client.receive();
    assert.ok(Array.isArray(batch));
    assert.deepEqual(batch.map((item) => item.id), [10, 11]);
    assert.deepEqual(batch[0].result, {});
    assert.ok(Array.isArray(batch[1].result.tools));
  })
);

test(
  "unknown method returns -32601",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(3, "resources/subscribe", { uri: "ouba://schema/story-graph-v1" });
    assert.equal(response.error.code, -32601);
  })
);

test(
  "malformed JSON returns -32700",
  withServer(async (client) => {
    client.sendRaw("{not json");
    const response = await client.receive();
    assert.equal(response.error.code, -32700);
  })
);

test(
  "non-object message returns -32600",
  withServer(async (client) => {
    client.sendRaw('"a string"');
    const response = await client.receive();
    assert.equal(response.error.code, -32600);
  })
);

test(
  "a notification without a method is ignored",
  withServer(async (client) => {
    client.sendRaw('{"jsonrpc":"2.0"}');
    const ping = await client.request(4, "ping");
    assert.deepEqual(ping.result, {});
  })
);

// ---------------------------------------------------------------------------
// tools/list
// ---------------------------------------------------------------------------

test(
  "tools/list exposes exactly four tools with schemas and annotations",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(2, "tools/list");
    const tools = response.result.tools;
    assert.deepEqual(
      tools.map((tool) => tool.name),
      ["validate_story_graph", "step_story_state", "query_ai_story_benchmark", "detect_state_drift"]
    );
    for (const tool of tools) {
      assert.equal(tool.inputSchema.type, "object");
      assert.equal(tool.outputSchema.type, "object");
      assert.equal(tool.annotations.readOnlyHint, true);
      assert.equal(tool.annotations.destructiveHint, false);
      assert.ok(tool.title.length > 5);
    }
  })
);

test(
  "required arguments are declared",
  withServer(async (client) => {
    await client.initialize();
    const tools = (await client.request(2, "tools/list")).result.tools;
    const byName = Object.fromEntries(tools.map((tool) => [tool.name, tool]));
    assert.deepEqual(byName.step_story_state.inputSchema.required, ["story", "choices"]);
    assert.deepEqual(byName.detect_state_drift.inputSchema.required, ["fact", "transcript"]);
  })
);

// ---------------------------------------------------------------------------
// Resources
// ---------------------------------------------------------------------------

test(
  "resources/list returns the benchmark matrix and the story schema",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(2, "resources/list");
    const resources = response.result.resources;
    assert.equal(resources.length, 2);
    const byUri = Object.fromEntries(resources.map((resource) => [resource.uri, resource]));
    assert.equal(byUri["ouba://benchmark/2026-10-platform-matrix"].mimeType, "application/json");
    assert.equal(byUri["ouba://schema/story-graph-v1"].mimeType, "application/schema+json");
  })
);

test(
  "resources/read returns the CC-BY-4.0 benchmark matrix",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(3, "resources/read", { uri: "ouba://benchmark/2026-10-platform-matrix" });
    const [content] = response.result.contents;
    assert.equal(content.uri, "ouba://benchmark/2026-10-platform-matrix");
    assert.equal(content.mimeType, "application/json");
    const payload = JSON.parse(content.text);
    assert.equal(payload.license, "CC-BY-4.0");
    assert.equal(payload.dataset_doi, "10.7910/DVN/YEBHQR");
    assert.equal(payload.benchmark.evaluation_date, "2026-11-15");
    assert.equal(payload.benchmark.platforms.length, 10);
    assert.ok(payload.citation.apa.includes("Ouba Studio. (2026)"));
  })
);

test(
  "resources/read returns the canonical story-graph JSON Schema",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(4, "resources/read", { uri: "ouba://schema/story-graph-v1" });
    const [content] = response.result.contents;
    assert.equal(content.mimeType, "application/schema+json");
    const schema = JSON.parse(content.text);
    assert.equal(schema.$id, "ouba://schema/story-graph-v1");
    assert.ok(schema.properties.scenes);
    assert.ok(schema.properties.startScene);
    assert.ok(schema.$defs.choice.properties.requires);
  })
);

test(
  "unknown resource returns -32002",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(5, "resources/read", { uri: "ouba://does-not/exist" });
    assert.equal(response.error.code, -32002);
  })
);

test(
  "resources/templates/list is empty",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(6, "resources/templates/list");
    assert.deepEqual(response.result, { resourceTemplates: [] });
  })
);

// ---------------------------------------------------------------------------
// validate_story_graph
// ---------------------------------------------------------------------------

test(
  "validate_story_graph passes a valid graph",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "validate_story_graph", { story: EXAMPLE });
    assert.equal(response.result.isError, false);
    const payload = response.result.structuredContent;
    assert.equal(payload.valid, true);
    assert.equal(payload.error_count, 0);
    assert.equal(payload.stats.scenes, 4);
    assert.equal(payload.stats.endings, 2);
    assert.equal(payload.stats.unreachable_scenes, 0);
    assert.deepEqual(JSON.parse(response.result.content[0].text), payload);
  })
);

test(
  "validate_story_graph flags missing targets",
  withServer(async (client) => {
    await client.initialize();
    const story = {
      startScene: "a",
      scenes: { a: { title: "A", body: "b", choices: [{ label: "Go", next: "ghost" }] } },
    };
    const response = await client.callTool(2, "validate_story_graph", { story });
    const payload = response.result.structuredContent;
    assert.equal(payload.valid, false);
    assert.ok(payload.errors.some((error) => error.code === "MISSING_TARGET"));
    assert.equal(payload.issues.missing_targets[0].next, "ghost");
  })
);

test(
  "validate_story_graph flags unreachable scenes, dead ends and loop traps",
  withServer(async (client) => {
    await client.initialize();
    const story = {
      startScene: "a",
      scenes: {
        a: { title: "A", body: "b", choices: [{ label: "Loop", next: "b" }] },
        b: { title: "B", body: "c", choices: [{ label: "Back", next: "a" }] },
        island: { title: "Island", body: "d", ending: true },
      },
    };
    const response = await client.callTool(2, "validate_story_graph", { story });
    const payload = response.result.structuredContent;
    const warningCodes = payload.warnings.map((warning) => warning.code);
    assert.ok(warningCodes.includes("UNREACHABLE_SCENE"));
    assert.ok(warningCodes.includes("LOOP_TRAP"));
    assert.deepEqual(payload.issues.unreachable_scenes, [{ scene: "island" }]);
    assert.deepEqual(payload.issues.loop_traps, [{ scene: "a" }, { scene: "b" }]);
  })
);

test(
  "validate_story_graph flags invalid guard predicates",
  withServer(async (client) => {
    await client.initialize();
    const story = {
      startScene: "a",
      initialState: { trust: 1 },
      scenes: {
        a: {
          title: "A",
          body: "b",
          choices: [
            { label: "Bad", next: "a", requires: { trust: "high" } },
            { label: "Unknown", next: "a", requires: { charisma: 2 } },
          ],
        },
      },
    };
    const response = await client.callTool(2, "validate_story_graph", { story });
    const payload = response.result.structuredContent;
    assert.equal(payload.valid, false);
    assert.ok(payload.errors.some((error) => error.code === "INVALID_GUARD"));
    assert.ok(payload.warnings.some((warning) => warning.code === "INVALID_GUARD_UNKNOWN_KEY"));
  })
);

test(
  "validate_story_graph reports a missing scenes map",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "validate_story_graph", { story: { startScene: "a" } });
    const payload = response.result.structuredContent;
    assert.equal(payload.valid, false);
    assert.equal(payload.errors[0].code, "SCHEMA_MISSING_SCENES");
  })
);

// ---------------------------------------------------------------------------
// step_story_state
// ---------------------------------------------------------------------------

test(
  "step_story_state applies additive effects and moves to the next scene",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "step_story_state", { story: EXAMPLE, choices: [0] });
    const payload = response.result.structuredContent;
    assert.equal(payload.final_scene, "stacks");
    assert.equal(payload.final_state.spark, 3);
    assert.equal(payload.turns, 1);
    assert.deepEqual(payload.history, ["arrival", "stacks"]);
    assert.equal(payload.stopped_reason, "choices_exhausted");
  })
);

test(
  "step_story_state blocks unmet guards without mutating state",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "step_story_state", { story: EXAMPLE, choices: [1] });
    const payload = response.result.structuredContent;
    assert.equal(payload.steps[0].status, "guard_blocked");
    assert.equal(payload.stopped_reason, "guard_blocked");
    assert.equal(payload.final_scene, "arrival");
    assert.equal(payload.final_state.trust, 1);
    assert.equal(payload.steps[0].unmet_guards[0].key, "trust");
  })
);

test(
  "step_story_state reaches an ending and stamps memory",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "step_story_state", {
      story: EXAMPLE,
      choices: [0, 0],
      remember: ["My cat's name is Marmalade."],
    });
    const payload = response.result.structuredContent;
    assert.equal(payload.final_scene, "folio");
    assert.equal(payload.final_state.trust, 3);
    assert.equal(payload.stopped_reason, "ending_reached");
    assert.deepEqual(payload.memory_trace, [{ turn: 0, fact: "My cat's name is Marmalade." }]);
  })
);

test(
  "step_story_state supports set/add/append/delete operators",
  withServer(async (client) => {
    await client.initialize();
    const story = {
      startScene: "a",
      initialState: { clues: [], curse: true, trust: 1 },
      scenes: {
        a: {
          title: "A",
          body: "b",
          choices: [
            {
              label: "Note",
              next: "b",
              effects: {
                clues: { op: "append", value: "x" },
                curse: { op: "delete" },
                trust: { op: "add", value: 4 },
                item: { op: "set", value: "amber ledger" },
              },
            },
          ],
        },
        b: { title: "B", body: "c", ending: true },
      },
    };
    const response = await client.callTool(2, "step_story_state", { story, choices: [0] });
    const payload = response.result.structuredContent;
    assert.deepEqual(payload.final_state.clues, ["x"]);
    assert.equal(payload.final_state.curse, undefined);
    assert.equal(payload.final_state.trust, 5);
    assert.equal(payload.final_state.item, "amber ledger");
    const ops = payload.steps[0].effects_applied.map((effect) => effect.op).sort();
    assert.deepEqual(ops, ["add", "append", "delete", "set"]);
  })
);

test(
  "step_story_state trace hash is deterministic and matches Python",
  withServer(async (client) => {
    await client.initialize();
    const first = await client.callTool(2, "step_story_state", { story: EXAMPLE, choices: [0, 0] });
    const second = await client.callTool(3, "step_story_state", { story: EXAMPLE, choices: [0, 0] });
    assert.equal(first.result.structuredContent.trace_hash, second.result.structuredContent.trace_hash);
    assert.equal(first.result.structuredContent.trace_hash, PINNED_TRACE_HASH);
    const other = await client.callTool(4, "step_story_state", { story: EXAMPLE, choices: [2] });
    assert.notEqual(other.result.structuredContent.trace_hash, PINNED_TRACE_HASH);
  })
);

test(
  "step_story_state accepts choice labels",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "step_story_state", {
      story: EXAMPLE,
      choices: ["hold his gaze"],
    });
    assert.equal(response.result.structuredContent.final_scene, "stacks");
  })
);

test(
  "step_story_state reports an out-of-range choice as isError",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "step_story_state", { story: EXAMPLE, choices: [99] });
    assert.equal(response.result.isError, true);
    assert.match(response.result.structuredContent.error, /out of range/);
  })
);

// ---------------------------------------------------------------------------
// query_ai_story_benchmark
// ---------------------------------------------------------------------------

test(
  "query_ai_story_benchmark returns all ten platforms",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "query_ai_story_benchmark", {});
    const payload = response.result.structuredContent;
    assert.equal(payload.count, 10);
    assert.equal(payload.benchmark.dataset_doi, "10.7910/DVN/YEBHQR");
    assert.equal(payload.benchmark.summary.probe_administered, 4);
    assert.ok(payload.citation.bibtex.includes("@dataset{"));
  })
);

test(
  "query_ai_story_benchmark filters by platform and alias",
  withServer(async (client) => {
    await client.initialize();
    const character = await client.callTool(2, "query_ai_story_benchmark", { platform: "Character.AI" });
    const characterPayload = character.result.structuredContent;
    assert.equal(characterPayload.count, 1);
    assert.equal(characterPayload.results[0].status, "fail");
    assert.equal(characterPayload.results[0].failure_mode, "F1");

    const dungeon = await client.callTool(3, "query_ai_story_benchmark", { platform: "aidungeon" });
    const dungeonPayload = dungeon.result.structuredContent;
    assert.equal(dungeonPayload.results[0].platform, "AI Dungeon");
    assert.equal(dungeonPayload.results[0].turns_completed, 7);
  })
);

test(
  "query_ai_story_benchmark filters by status",
  withServer(async (client) => {
    await client.initialize();
    const pass = await client.callTool(2, "query_ai_story_benchmark", { status: "pass" });
    assert.deepEqual(
      pass.result.structuredContent.results.map((p) => p.platform),
      ["Ouba", "Talkie", "AI Dungeon"]
    );
    const censored = await client.callTool(3, "query_ai_story_benchmark", { status: "right_censored" });
    assert.deepEqual(
      censored.result.structuredContent.results.map((p) => p.platform),
      ["Janitor AI", "Talefy", "Joyland", "NovelAI"]
    );
    const untestable = await client.callTool(4, "query_ai_story_benchmark", { status: "untestable" });
    assert.deepEqual(
      untestable.result.structuredContent.results.map((p) => p.platform),
      ["Chai", "Galatea"]
    );
  })
);

test(
  "query_ai_story_benchmark warns on unknown platforms",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "query_ai_story_benchmark", { platform: "Myspace" });
    const payload = response.result.structuredContent;
    assert.equal(payload.count, 0);
    assert.match(payload.warnings[0], /known platforms/);
  })
);

test(
  "benchmark tool and resource agree",
  withServer(async (client) => {
    await client.initialize();
    const tool = await client.callTool(2, "query_ai_story_benchmark", {});
    const resource = await client.request(3, "resources/read", { uri: "ouba://benchmark/2026-10-platform-matrix" });
    const payload = JSON.parse(resource.result.contents[0].text);
    assert.deepEqual(tool.result.structuredContent.results, payload.benchmark.platforms);
  })
);

// ---------------------------------------------------------------------------
// detect_state_drift
// ---------------------------------------------------------------------------

const PLANTED = { key: "cat_name", expected_value: "Marmalade", planted_turn: 2 };

test(
  "detect_state_drift returns PASS on verbatim recall",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "detect_state_drift", {
      fact: PLANTED,
      transcript: ["Hello.", "My cat's name is Marmalade.", "Lovely.", "And now?", "Marmalade, of course."],
      probe_turn: 5,
    });
    const payload = response.result.structuredContent;
    assert.equal(payload.verdict, "PASS");
    assert.equal(payload.passed, true);
    assert.equal(payload.drift_detected, false);
    assert.deepEqual(payload.evidence.recall_turns, [5]);
  })
);

test(
  "detect_state_drift classifies omission as F1",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "detect_state_drift", {
      fact: PLANTED,
      transcript: ["Hello.", "My cat's name is Marmalade.", "Nice weather.", "Anyway.", "Who is your cat?"],
      probe_turn: 5,
    });
    const payload = response.result.structuredContent;
    assert.equal(payload.verdict, "F1_OMISSION");
    assert.equal(payload.passed, false);
    assert.equal(payload.mode, "F1");
  })
);

test(
  "detect_state_drift classifies contradiction as F1",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "detect_state_drift", {
      fact: { ...PLANTED, wrong_values: ["Rex"] },
      transcript: ["Hello.", "My cat's name is Marmalade.", "Nice weather.", "Your cat is Rex.", "Right."],
      probe_turn: 5,
    });
    const payload = response.result.structuredContent;
    assert.equal(payload.verdict, "F1_CONTRADICTION");
    assert.deepEqual(payload.evidence.contradiction_turns, [4]);
  })
);

test(
  "detect_state_drift classifies transient degradation as F4",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "detect_state_drift", {
      fact: PLANTED,
      transcript: ["Hello.", "My cat's name is Marmalade.", "Sure.", "", "Still there?", "Marmalade."],
      probe_turn: 6,
    });
    const payload = response.result.structuredContent;
    assert.equal(payload.verdict, "F4_TRANSIENT_DEGRADATION");
    assert.equal(payload.passed, true);
    assert.equal(payload.evidence.stall_detected, true);
  })
);

test(
  "detect_state_drift classifies gating censoring as F3",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "detect_state_drift", {
      fact: PLANTED,
      transcript: ["Hello.", "My cat's name is Marmalade."],
    });
    const payload = response.result.structuredContent;
    assert.equal(payload.verdict, "F3_GATING_CENSORING");
    assert.equal(payload.passed, null);
    assert.equal(payload.evidence.probe_reached, false);
  })
);

test(
  "detect_state_drift classifies empty turns as F2",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "detect_state_drift", {
      fact: PLANTED,
      transcript: ["Hello.", "My cat's name is Marmalade.", "", "", "Anyone?"],
      probe_turn: 5,
    });
    const payload = response.result.structuredContent;
    assert.equal(payload.verdict, "F2_SESSION_NON_PERSISTENCE");
    assert.deepEqual(payload.evidence.empty_turns, [3, 4]);
  })
);

test(
  "detect_state_drift flags an unplanted fact",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "detect_state_drift", {
      fact: PLANTED,
      transcript: ["Hello.", "Nice weather.", "Goodbye."],
    });
    assert.equal(response.result.structuredContent.verdict, "FACT_NOT_PLANTED");
  })
);

test(
  "detect_state_drift exposes the five-mode taxonomy",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "detect_state_drift", {
      fact: PLANTED,
      transcript: ["Hello.", "My cat's name is Marmalade.", "Marmalade"],
    });
    const payload = response.result.structuredContent;
    assert.deepEqual(payload.taxonomy.map((mode) => mode.code), ["F1", "F2", "F3", "F4", "F5"]);
    assert.equal(payload.taxonomy_source.doi, "10.5281/zenodo.24549412");
    assert.deepEqual(
      payload.per_turn.map((entry) => entry.relation),
      ["at_or_before_planting", "at_or_before_planting", "recalled"]
    );
  })
);

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

test(
  "unknown tools return -32602 and list the available tools",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(2, "tools/call", { name: "nope", arguments: {} });
    assert.equal(response.error.code, -32602);
    assert.match(response.error.message, /step_story_state/);
  })
);

test(
  "malformed arguments return -32602",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.request(2, "tools/call", {
      name: "validate_story_graph",
      arguments: "not-an-object",
    });
    assert.equal(response.error.code, -32602);
  })
);

test(
  "broken stories return isError instead of a protocol error",
  withServer(async (client) => {
    await client.initialize();
    const response = await client.callTool(2, "step_story_state", { story: { scenes: {} }, choices: [0] });
    assert.equal(response.error, undefined);
    assert.equal(response.result.isError, true);
    assert.match(response.result.structuredContent.error, /scenes/);
  })
);
