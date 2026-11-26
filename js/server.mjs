#!/usr/bin/env node
/**
 * server.mjs — zero-dependency MCP server over stdio (JSON-RPC 2.0).
 *
 * Implements Model Context Protocol `2024-11-05` and `2025-03-26`:
 * initialize, notifications/initialized, ping, tools/list, tools/call,
 * resources/list, resources/read.
 *
 * Run: `node js/server.mjs`, `npx branching-story-mcp`, or
 * `deno run -A jsr.io/@ouba-studio/branching-story-mcp/server`.
 *
 * MIT License — Ouba Studio <team@ouba.art> — https://www.ouba.art/
 */

import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  BENCHMARK,
  EXPLORER_URL,
  benchmarkCitation,
  queryBenchmark,
} from "./benchmark.mjs";
import {
  SERVER_NAME,
  STORY_GRAPH_SCHEMA,
  VERSION,
  detectStateDrift,
  normalizeStory,
  stepStoryState,
  validateStoryGraph,
} from "./kernel.mjs";

export const SERVER_INFO = { name: SERVER_NAME, version: VERSION };
const SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26"];
const DEFAULT_PROTOCOL_VERSION = "2025-03-26";

const INSTRUCTIONS =
  "branching-story-mcp exposes Ouba Studio's deterministic branching-story-kit " +
  "story-state kernel and the CC-BY-4.0 2026 Consumer AI Story Continuity " +
  "Benchmark (doi:10.7910/DVN/YEBHQR). Use validate_story_graph before stepping, " +
  "step_story_state for zero-drift state transitions, query_ai_story_benchmark for " +
  "verified per-platform continuity results, and detect_state_drift to classify a "  +
  "transcript against the five-mode silent state drift taxonomy. " +
  `Interactive explorer: ${EXPLORER_URL}`;

const STORY_PROPERTY = {
  type: "object",
  description:
    "A branching-story-kit v1 story graph: {id?, title?, startScene (or legacy start), " +
    "initialState?, scenes}. Scenes map id -> {title, body, ending?, choices?}. " +
    "Choices carry label, next (or href), optional requires {key: minimum} and optional " +
    "effects {key: value | {op: set|add|append|delete, value}}.",
};

export const TOOLS = [
  {
    name: "validate_story_graph",
    title: "Validate a branching story graph",
    description:
      "Validate a branching-story-kit JSON scene graph. Checks the schema, detects " +
      "missing choice targets, unreachable scenes, dead-end loops and invalid guard " +
      "predicates, and returns structured diagnostics with issue codes, stats and a " +
      "pass/fail verdict.",
    inputSchema: {
      type: "object",
      properties: {
        story: STORY_PROPERTY,
        scenes: { type: "object", description: "Alternative to `story`: the scenes map." },
        startScene: { type: "string", description: "Alternative to `story`: the start scene id." },
        initialState: {
          type: "object",
          description: "Alternative to `story`: the initial state vector.",
        },
      },
      additionalProperties: true,
    },
    outputSchema: { type: "object", additionalProperties: true },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: "step_story_state",
    title: "Advance deterministic story state",
    description:
      "Run the deterministic story-state reducer for one or more player choices. " +
      "Evaluates `requires` guards, applies `set` / `add` / `append` effects through a " +
      "single write path, and returns the next scene, updated state, fired guards, " +
      "available choices and a turn-stamped memory trace with a verifiable SHA-256 " +
      "trace hash. Zero silent state drift.",
    inputSchema: {
      type: "object",
      properties: {
        story: STORY_PROPERTY,
        choices: {
          type: "array",
          items: { anyOf: [{ type: "integer" }, { type: "string" }, { type: "object" }] },
          description:
            "Ordered player choices. Each entry is an integer index into the current " +
            "scene's choices, a case-insensitive choice label, or {index}/{label}.",
        },
        state: {
          type: "object",
          description: "Optional state overrides applied on top of initialState.",
        },
        memory: {
          type: "array",
          items: { anyOf: [{ type: "string" }, { type: "object" }] },
          description: "Optional prior memory log: strings or {turn, fact} objects.",
        },
        remember: {
          type: "array",
          items: { anyOf: [{ type: "string" }, { type: "object" }] },
          description: "Facts to plant in the turn-stamped memory log before stepping.",
        },
        startScene: { type: "string", description: "Optional override for the entry scene." },
      },
      required: ["story", "choices"],
      additionalProperties: true,
    },
    outputSchema: { type: "object", additionalProperties: true },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: "query_ai_story_benchmark",
    title: "Query the 2026 AI story continuity benchmark",
    description:
      "Query the verified Nov 15 2026 10-Platform Consumer AI Story Continuity Benchmark " +
      "(doi:10.7910/DVN/YEBHQR): Ouba 20t verbatim PASS, Talkie 20t PASS, AI Dungeon 7t " +
      "verbatim PASS, Character.AI 20t FAIL (silent state loss), Janitor AI / Talefy / " +
      "Joyland / NovelAI right-censored, Chai / Galatea untestable. Optional `platform` " +
      "or `status` filter. Returns structured JSON plus full APA/BibTeX citation and the " +
      "interactive benchmark explorer URL.",
    inputSchema: {
      type: "object",
      properties: {
        platform: {
          type: "string",
          description: "Platform name or alias, e.g. 'Character.AI', 'talkie', 'ai-dungeon'.",
        },
        status: {
          type: "string",
          enum: ["pass", "fail", "right_censored", "untestable", "tested"],
          description: "Optional outcome filter.",
        },
      },
      additionalProperties: true,
    },
    outputSchema: { type: "object", additionalProperties: true },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  {
    name: "detect_state_drift",
    title: "Detect silent state drift in a transcript",
    description:
      "Given a planted fact {key, expected_value, planted_turn} and a transcript of turns, " +
      "check deterministic recall / contradiction / omission and classify the session " +
      "against the five-mode silent state drift taxonomy (F1 silent state loss, F2 session " +
      "non-persistence, F3 gating censoring, F4 transient service degradation, F5 platform " +
      "delisting) from doi:10.5281/zenodo.24549412.",
    inputSchema: {
      type: "object",
      properties: {
        fact: {
          type: "object",
          properties: {
            key: { type: "string", description: "State key, e.g. 'cat_name'." },
            expected_value: { type: "string", description: "The planted value, e.g. 'Marmalade'." },
            planted_turn: {
              type: "integer",
              description: "1-based turn where the fact was planted.",
            },
            wrong_values: {
              type: "array",
              items: { type: "string" },
              description: "Values that would contradict the planted fact.",
            },
            aliases: {
              type: "array",
              items: { type: "string" },
              description: "Accepted spellings of the expected value.",
            },
            contradiction_mode: {
              type: "string",
              enum: ["wrong_values", "key_mention_without_value"],
              description: "How contradictions are detected (default: wrong_values).",
            },
          },
          required: ["key", "expected_value"],
          additionalProperties: true,
        },
        transcript: {
          type: "array",
          items: {
            anyOf: [
              { type: "string" },
              {
                type: "object",
                properties: {
                  turn: { type: "integer" },
                  speaker: { type: "string" },
                  text: { type: "string" },
                },
                required: ["text"],
              },
            ],
          },
          description: "Conversation turns, oldest first.",
        },
        probe_turn: {
          type: "integer",
          description: "Turn at which recall is probed (default: last turn).",
        },
        min_gap: {
          type: "integer",
          description:
            "Minimum turns after planting before a session counts as probed (default 2).",
        },
        delisted: {
          type: "boolean",
          description: "Set true when the platform was delisted (forces F5).",
        },
      },
      required: ["fact", "transcript"],
      additionalProperties: true,
    },
    outputSchema: { type: "object", additionalProperties: true },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
];

export const RESOURCE_BENCHMARK_URI = "ouba://benchmark/2026-10-platform-matrix";
export const RESOURCE_SCHEMA_URI = "ouba://schema/story-graph-v1";

export const RESOURCES = [
  {
    uri: RESOURCE_BENCHMARK_URI,
    name: "2026-10-platform-matrix",
    title: "2026 Consumer AI Story Continuity Benchmark — 10-platform matrix",
    description:
      "Full CC-BY-4.0 per-platform matrix (evaluation date 2026-11-15, " +
      "doi:10.7910/DVN/YEBHQR): status, turns completed, turn-15 recall, TTFS, latency, " +
      "ads, signup gate, failure mode and notes for all 10 platforms.",
    mimeType: "application/json",
  },
  {
    uri: RESOURCE_SCHEMA_URI,
    name: "story-graph-v1",
    title: "branching-story-kit story graph v1 JSON Schema",
    description:
      "Canonical JSON Schema for branching-story-kit scene graphs (scenes, startScene, initialState).",
    mimeType: "application/schema+json",
  },
];

class ToolError extends Error {
  constructor(message, details) {
    super(message);
    this.name = "ToolError";
    this.details = details || {};
  }
}

class InvalidParams extends Error {
  constructor(message) {
    super(message);
    this.name = "InvalidParams";
  }
}

function requireObject(args) {
  if (args === undefined || args === null) return {};
  if (typeof args !== "object" || Array.isArray(args)) {
    throw new InvalidParams("tool arguments must be a JSON object");
  }
  return args;
}

function coerceStory(args) {
  if (args.story && typeof args.story === "object" && !Array.isArray(args.story)) return args.story;
  if (args.scenes && typeof args.scenes === "object" && !Array.isArray(args.scenes)) {
    return {
      id: args.id,
      title: args.title,
      startScene: args.startScene || args.start,
      initialState: args.initialState || {},
      scenes: args.scenes,
    };
  }
  throw new InvalidParams(
    "provide a `story` object (or the `scenes`, `startScene` and `initialState` fields)"
  );
}

function toolValidateStoryGraph(args) {
  return validateStoryGraph(coerceStory(args));
}

function toolStepStoryState(args) {
  const story = coerceStory(args);
  const choices = args.choices;
  if (choices === undefined || choices === null) {
    throw new InvalidParams("`choices` is required: an array of choice indexes or labels");
  }
  if (!Array.isArray(choices)) throw new InvalidParams("`choices` must be an array");
  if (args.state !== undefined && args.state !== null && (typeof args.state !== "object" || Array.isArray(args.state))) {
    throw new InvalidParams("`state` must be an object");
  }
  return stepStoryState(story, choices, {
    state: args.state,
    memory: args.memory,
    remember: args.remember,
    startScene: args.startScene,
  });
}

function toolQueryAiStoryBenchmark(args) {
  if (args.platform !== undefined && args.platform !== null && typeof args.platform !== "string") {
    throw new InvalidParams("`platform` must be a string");
  }
  if (args.status !== undefined && args.status !== null && typeof args.status !== "string") {
    throw new InvalidParams("`status` must be a string");
  }
  return queryBenchmark({ platform: args.platform, status: args.status });
}

function toolDetectStateDrift(args) {
  if (args.fact === undefined || args.fact === null) {
    throw new InvalidParams("`fact` is required: {key, expected_value, planted_turn?}");
  }
  if (args.transcript === undefined || args.transcript === null) {
    throw new InvalidParams("`transcript` is required: an array of turns");
  }
  if (args.probe_turn !== undefined && args.probe_turn !== null && !Number.isInteger(args.probe_turn)) {
    throw new InvalidParams("`probe_turn` must be an integer");
  }
  if (args.min_gap !== undefined && args.min_gap !== null && (!Number.isInteger(args.min_gap) || args.min_gap < 1)) {
    throw new InvalidParams("`min_gap` must be a positive integer");
  }
  if (args.delisted !== undefined && args.delisted !== null && typeof args.delisted !== "boolean") {
    throw new InvalidParams("`delisted` must be a boolean");
  }
  return detectStateDrift(args.fact, args.transcript, {
    probeTurn: args.probe_turn,
    minGap: args.min_gap,
    delisted: args.delisted === true,
  });
}

const TOOL_HANDLERS = {
  validate_story_graph: toolValidateStoryGraph,
  step_story_state: toolStepStoryState,
  query_ai_story_benchmark: toolQueryAiStoryBenchmark,
  detect_state_drift: toolDetectStateDrift,
};

function readResource(uri) {
  let payload;
  let mime;
  if (uri === RESOURCE_BENCHMARK_URI) {
    payload = {
      license: BENCHMARK.license,
      license_url: BENCHMARK.license_url,
      dataset_doi: BENCHMARK.dataset_doi,
      dataset_url: BENCHMARK.dataset_url,
      explorer_url: EXPLORER_URL,
      citation: benchmarkCitation(),
      benchmark: BENCHMARK,
    };
    mime = "application/json";
  } else if (uri === RESOURCE_SCHEMA_URI) {
    payload = STORY_GRAPH_SCHEMA;
    mime = "application/schema+json";
  } else {
    throw new ToolError(`unknown resource URI: ${uri}`);
  }
  return { contents: [{ uri, mimeType: mime, text: JSON.stringify(payload) }] };
}

function result(id, value) {
  return { jsonrpc: "2.0", id, result: value };
}

function error(id, code, message, data) {
  const err = { code, message };
  if (data !== undefined) err.data = data;
  return { jsonrpc: "2.0", id, error: err };
}

function toolContent(payload, isError = false) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
    structuredContent: payload,
    isError,
  };
}

function handleInitialize(params) {
  const requested = params && params.protocolVersion;
  const protocol = SUPPORTED_PROTOCOL_VERSIONS.includes(requested) ? requested : DEFAULT_PROTOCOL_VERSION;
  return {
    protocolVersion: protocol,
    capabilities: {
      tools: { listChanged: false },
      resources: { subscribe: false, listChanged: false },
    },
    serverInfo: SERVER_INFO,
    instructions: INSTRUCTIONS,
  };
}

function handleToolsCall(params) {
  if (!params || typeof params !== "object" || Array.isArray(params)) {
    throw new InvalidParams("tools/call params must be an object");
  }
  const { name } = params;
  if (typeof name !== "string") throw new InvalidParams("tools/call requires a string `name`");
  const handler = TOOL_HANDLERS[name];
  if (!handler) {
    throw new InvalidParams(
      `unknown tool '${name}'; available tools: ` + Object.keys(TOOL_HANDLERS).sort().join(", ")
    );
  }
  const args = requireObject(params.arguments);
  try {
    return toolContent(handler(args));
  } catch (err) {
    if (err instanceof ToolError) {
      return toolContent(Object.assign({ ok: false, error: err.message }, err.details), true);
    }
    if (err instanceof Error && err.name === "ToolError") {
      return toolContent(Object.assign({ ok: false, error: err.message }, err.details), true);
    }
    if (err instanceof Error && !(err instanceof InvalidParams)) {
      return toolContent({ ok: false, error: err.message }, true);
    }
    throw err;
  }
}

export function handleMessage(message) {
  if (Array.isArray(message)) {
    const batch = message.map(handleMessage).filter((r) => r !== null);
    return batch.length ? batch : null;
  }
  if (!message || typeof message !== "object" || Array.isArray(message)) {
    return error(null, -32600, "Invalid Request: message must be an object");
  }

  const method = message.method;
  const id = message.id;
  const isNotification = !("id" in message);

  if (typeof method !== "string") {
    return isNotification ? null : error(id, -32600, "Invalid Request: missing method");
  }
  if (isNotification) return null;

  const params = message.params === undefined ? {} : message.params;

  if (method === "initialize") return result(id, handleInitialize(params));
  if (method === "ping") return result(id, {});
  if (method === "tools/list") return result(id, { tools: TOOLS });
  if (method === "resources/list") return result(id, { resources: RESOURCES });
  if (method === "resources/templates/list") return result(id, { resourceTemplates: [] });
  if (method === "prompts/list") return result(id, { prompts: [] });
  if (method === "tools/call") {
    try {
      return result(id, handleToolsCall(params));
    } catch (err) {
      if (err instanceof InvalidParams) return error(id, -32602, err.message);
      throw err;
    }
  }
  if (method === "resources/read") {
    if (!params || typeof params.uri !== "string") {
      return error(id, -32602, "resources/read requires a string `uri`");
    }
    try {
      return result(id, readResource(params.uri));
    } catch (err) {
      if (err instanceof ToolError) return error(id, -32002, err.message);
      throw err;
    }
  }
  if (method === "logging/setLevel") return result(id, {});
  return error(id, -32601, `Method not found: ${method}`);
}

function emit(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

export function main() {
  const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
  rl.on("line", (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let message;
    try {
      message = JSON.parse(trimmed);
    } catch (err) {
      emit(error(null, -32700, `Parse error: ${err.message}`));
      return;
    }
    const response = handleMessage(message);
    if (response !== null) emit(response);
  });
  return new Promise((resolve) => rl.on("close", () => resolve(0)));
}

const isDirectRun = (() => {
  try {
    return process.argv[1] ? fileURLToPath(import.meta.url) === fileURLToPath(pathToFileURL(process.argv[1])) : false;
  } catch {
    return false;
  }
})();

if (isDirectRun) {
  main().then((code) => process.exit(code));
}
