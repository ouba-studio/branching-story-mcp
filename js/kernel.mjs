/**
 * kernel.mjs — deterministic story-state kernel (JavaScript/ESM mirror).
 *
 * Behaviour-identical to `branching_story_mcp/kernel.py`: same validation issue
 * codes, same guard/effect semantics, same canonical JSON, same trace hashes.
 *
 * Zero dependencies. Node >= 18, Deno >= 1.40, Bun >= 1.0.
 * MIT License — Ouba Studio <team@ouba.art> — https://www.ouba.art/
 */

import { createHash } from "node:crypto";

export const VERSION = "1.0.0";
export const SERVER_NAME = "branching-story-mcp";

const clone = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));

/** Collapse integral numbers so hashes match the Python implementation. */
function normalizeNumbers(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) && Number.isInteger(value) ? Math.trunc(value) : value;
  }
  if (Array.isArray(value)) return value.map(normalizeNumbers);
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value)) out[String(key)] = normalizeNumbers(value[key]);
    return out;
  }
  return value;
}

/** Deterministic JSON: sorted keys, no whitespace, integral floats as integers. */
export function canonicalJson(value) {
  const sortDeep = (input) => {
    if (Array.isArray(input)) return input.map(sortDeep);
    if (input && typeof input === "object") {
      const out = {};
      for (const key of Object.keys(input).sort()) out[key] = sortDeep(input[key]);
      return out;
    }
    return input;
  };
  return JSON.stringify(sortDeep(normalizeNumbers(value)));
}

export function sha256Hex(text) {
  return createHash("sha256").update(String(text), "utf8").digest("hex");
}

export const STORY_GRAPH_SCHEMA = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "ouba://schema/story-graph-v1",
  title: "branching-story-kit story graph v1",
  type: "object",
  required: ["scenes", "startScene"],
  properties: {
    id: { type: "string", description: "Stable story identifier." },
    title: { type: "string", description: "Human-readable story title." },
    startScene: {
      type: "string",
      description: "Scene id the reader enters first. The legacy alias `start` is accepted.",
    },
    start: { type: "string", description: "Legacy alias for startScene." },
    initialState: {
      type: "object",
      description: "Initial story-state vector (relationship meters, flags, inventory).",
      additionalProperties: { type: ["number", "string", "boolean", "array", "null"] },
    },
    scenes: {
      type: "object",
      description: "Map of scene id -> scene definition.",
      additionalProperties: { $ref: "#/$defs/scene" },
    },
  },
  $defs: {
    scene: {
      type: "object",
      required: ["title", "body"],
      properties: {
        title: { type: "string" },
        body: { type: "string", description: "Scene prose. `{{key}}` interpolates state." },
        ending: { type: "boolean", default: false },
        choices: { type: "array", items: { $ref: "#/$defs/choice" } },
      },
    },
    choice: {
      type: "object",
      required: ["label"],
      properties: {
        label: { type: "string" },
        next: { type: "string", description: "Target scene id." },
        href: { type: "string", description: "External link target (no state change)." },
        requires: {
          type: "object",
          description: "Guard predicate: state key -> minimum numeric value.",
          additionalProperties: { type: "number" },
        },
        effects: {
          type: "object",
          description:
            "State mutations. Scalar numbers add, strings/booleans assign, and " +
            "{op: set|add|append|delete, value} gives explicit control.",
          additionalProperties: true,
        },
      },
    },
    effectOp: {
      type: "object",
      required: ["op"],
      properties: { op: { type: "string", enum: ["set", "add", "append", "delete"] }, value: {} },
    },
  },
};

export function normalizeStory(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("story must be a JSON object");
  }
  const scenes = raw.scenes;
  if (!scenes || typeof scenes !== "object" || Array.isArray(scenes) || Object.keys(scenes).length === 0) {
    throw new Error("story.scenes must be a non-empty object");
  }
  const start = raw.startScene || raw.start;
  const initial = raw.initialState;
  if (initial !== undefined && initial !== null && (typeof initial !== "object" || Array.isArray(initial))) {
    throw new Error("story.initialState must be an object when present");
  }
  return {
    id: raw.id,
    title: raw.title,
    startScene: start,
    initialState: Object.assign({}, initial || {}),
    scenes,
  };
}

function issue(code, message, extra) {
  return Object.assign({ code, message }, extra || {});
}

function numeric(value) {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function effectKeys(scenes) {
  const keys = new Set();
  for (const scene of Object.values(scenes)) {
    if (!scene || typeof scene !== "object") continue;
    for (const choice of scene.choices || []) {
      if (choice && typeof choice === "object" && choice.effects && typeof choice.effects === "object") {
        for (const key of Object.keys(choice.effects)) keys.add(String(key));
      }
    }
  }
  return keys;
}

function stats(scenes, choices, endings, reachable, unreachable) {
  return {
    scenes,
    choices,
    endings,
    reachable_scenes: reachable,
    unreachable_scenes: unreachable,
  };
}

function validationResult(errors, warnings, issues, statsObj) {
  return {
    valid: errors.length === 0,
    error_count: errors.length,
    warning_count: warnings.length,
    errors,
    warnings,
    issues,
    stats: statsObj,
  };
}

export function validateStoryGraph(story) {
  const errors = [];
  const warnings = [];
  const issues = {
    missing_targets: [],
    unreachable_scenes: [],
    dead_ends: [],
    loop_traps: [],
    invalid_guards: [],
  };

  if (!story || typeof story !== "object" || Array.isArray(story)) {
    return validationResult(
      [issue("SCHEMA_INVALID_STORY", "story must be a JSON object", { path: "story" })],
      [],
      issues,
      stats(0, 0, 0, 0, 0)
    );
  }

  const scenes = story.scenes;
  if (!scenes || typeof scenes !== "object" || Array.isArray(scenes) || Object.keys(scenes).length === 0) {
    return validationResult(
      [issue("SCHEMA_MISSING_SCENES", "story.scenes must be a non-empty object", { path: "scenes" })],
      [],
      issues,
      stats(0, 0, 0, 0, 0)
    );
  }

  const start = story.startScene || story.start;
  if (typeof start !== "string" || !start.trim()) {
    errors.push(
      issue("SCHEMA_MISSING_START", "story.startScene (or legacy story.start) is required", {
        path: "startScene",
      })
    );
  } else if (!(start in scenes)) {
    errors.push(
      issue("SCHEMA_START_NOT_FOUND", `start scene '${start}' is not defined in story.scenes`, {
        path: "startScene",
        scene: start,
      })
    );
  }

  let initial = story.initialState;
  if (initial === undefined || initial === null) initial = {};
  if (typeof initial !== "object" || Array.isArray(initial)) {
    errors.push(issue("SCHEMA_INVALID_INITIAL_STATE", "story.initialState must be an object", { path: "initialState" }));
    initial = {};
  }

  const produced = effectKeys(scenes);
  const knownStateKeys = new Set([...Object.keys(initial), ...produced]);

  let choiceCount = 0;
  let endingCount = 0;
  const edges = {};

  for (const [sceneId, scene] of Object.entries(scenes)) {
    if (!scene || typeof scene !== "object" || Array.isArray(scene)) {
      errors.push(issue("SCHEMA_INVALID_SCENE", `scene '${sceneId}' must be an object`, { path: `scenes.${sceneId}` }));
      continue;
    }

    if (typeof scene.title !== "string" || !scene.title.trim()) {
      warnings.push(issue("SCENE_MISSING_TITLE", `scene '${sceneId}' has no title`, { path: `scenes.${sceneId}.title` }));
    }
    if (typeof scene.body !== "string" || !scene.body.trim()) {
      warnings.push(issue("SCENE_MISSING_BODY", `scene '${sceneId}' has no body prose`, { path: `scenes.${sceneId}.body` }));
    }
    if (typeof scene.ending !== "undefined" && typeof scene.ending !== "boolean") {
      errors.push(
        issue("SCENE_INVALID_ENDING", `scene '${sceneId}'.ending must be a boolean`, {
          path: `scenes.${sceneId}.ending`,
        })
      );
    }
    if (scene.ending === true) endingCount += 1;

    let choices = scene.choices;
    if (choices === undefined || choices === null) choices = [];
    if (!Array.isArray(choices)) {
      errors.push(
        issue("SCENE_INVALID_CHOICES", `scene '${sceneId}'.choices must be an array`, {
          path: `scenes.${sceneId}.choices`,
        })
      );
      choices = [];
    }

    const outgoing = [];
    choices.forEach((choice, index) => {
      if (!choice || typeof choice !== "object" || Array.isArray(choice)) {
        errors.push(
          issue("SCHEMA_INVALID_CHOICE", `scene '${sceneId}' choice #${index} must be an object`, {
            path: `scenes.${sceneId}.choices[${index}]`,
          })
        );
        return;
      }
      choiceCount += 1;
      const label = choice.label === undefined ? "" : choice.label;

      const next = choice.next;
      const href = choice.href;
      if (typeof next !== "string" || !next) {
        if (typeof href !== "string" || !href) {
          errors.push(
            issue(
              "SCHEMA_CHOICE_NO_TARGET",
              `scene '${sceneId}' choice #${index} ('${label}') needs a 'next' scene id or an 'href'`,
              { path: `scenes.${sceneId}.choices[${index}]` }
            )
          );
        }
        return;
      }

      if (!(next in scenes)) {
        const record = { scene: sceneId, choice_index: index, label, next };
        issues.missing_targets.push(record);
        errors.push(
          issue("MISSING_TARGET", `scene '${sceneId}' choice #${index} links to missing scene '${next}'`, {
            path: `scenes.${sceneId}.choices[${index}].next`,
            ...record,
          })
        );
      } else {
        outgoing.push(next);
      }

      const requires = choice.requires;
      if (requires !== undefined && requires !== null) {
        if (typeof requires !== "object" || Array.isArray(requires)) {
          const record = {
            scene: sceneId,
            choice_index: index,
            label,
            reason: "requires must be an object mapping state keys to numeric minimums",
          };
          issues.invalid_guards.push(record);
          errors.push(
            issue("INVALID_GUARD", `scene '${sceneId}' choice #${index} has a non-object 'requires' guard`, {
              path: `scenes.${sceneId}.choices[${index}].requires`,
              ...record,
            })
          );
        } else {
          for (const [key, minimum] of Object.entries(requires)) {
            if (numeric(minimum) === null) {
              const record = {
                scene: sceneId,
                choice_index: index,
                label,
                key: String(key),
                reason: `requirement for '${key}' must be a number`,
              };
              issues.invalid_guards.push(record);
              errors.push(
                issue("INVALID_GUARD", `scene '${sceneId}' choice #${index} guard for '${key}' is not numeric`, {
                  path: `scenes.${sceneId}.choices[${index}].requires.${key}`,
                  ...record,
                })
              );
            } else if (!knownStateKeys.has(String(key))) {
              const record = {
                scene: sceneId,
                choice_index: index,
                label,
                key: String(key),
                reason: `guard references unknown state key '${key}'`,
              };
              issues.invalid_guards.push(record);
              warnings.push(
                issue(
                  "INVALID_GUARD_UNKNOWN_KEY",
                  `scene '${sceneId}' choice #${index} guards on undeclared state key '${key}'`,
                  { path: `scenes.${sceneId}.choices[${index}].requires.${key}`, ...record }
                )
              );
            }
          }
        }
      }

      if (choice.effects !== undefined && choice.effects !== null && typeof choice.effects !== "object") {
        errors.push(
          issue("SCHEMA_INVALID_EFFECTS", `scene '${sceneId}' choice #${index} has a non-object 'effects' value`, {
            path: `scenes.${sceneId}.choices[${index}].effects`,
          })
        );
      }
    });

    edges[sceneId] = outgoing;
  }

  const reachable = new Set();
  if (typeof start === "string" && start in scenes) {
    const stack = [start];
    while (stack.length) {
      const node = stack.pop();
      if (reachable.has(node)) continue;
      reachable.add(node);
      for (const next of edges[node] || []) stack.push(next);
    }
  }
  const unreachable = reachable.size ? Object.keys(scenes).filter((s) => !reachable.has(s)).sort() : [];
  for (const sceneId of unreachable) {
    issues.unreachable_scenes.push({ scene: sceneId });
    warnings.push(
      issue("UNREACHABLE_SCENE", `scene '${sceneId}' cannot be reached from the start scene`, {
        path: `scenes.${sceneId}`,
        scene: sceneId,
      })
    );
  }

  for (const [sceneId, scene] of Object.entries(scenes)) {
    if (!scene || typeof scene !== "object") continue;
    if (scene.ending === true) continue;
    if (!(edges[sceneId] || []).length && !(scene.choices || []).length) {
      issues.dead_ends.push({ scene: sceneId });
      warnings.push(
        issue("DEAD_END", `scene '${sceneId}' is not marked ending and has no choices`, {
          path: `scenes.${sceneId}`,
          scene: sceneId,
        })
      );
    }
  }

  const terminals = new Set(
    Object.entries(scenes)
      .filter(
        ([sid, scene]) =>
          scene && typeof scene === "object" && (scene.ending === true || !(edges[sid] || []).length)
      )
      .map(([sid]) => sid)
  );
  const canExit = new Set(terminals);
  let changed = true;
  while (changed) {
    changed = false;
    for (const sid of Object.keys(scenes)) {
      if (canExit.has(sid)) continue;
      if ((edges[sid] || []).some((node) => canExit.has(node))) {
        canExit.add(sid);
        changed = true;
      }
    }
  }
  for (const sceneId of Object.keys(scenes).filter((s) => reachable.has(s) && !canExit.has(s)).sort()) {
    issues.loop_traps.push({ scene: sceneId });
    warnings.push(
      issue("LOOP_TRAP", `scene '${sceneId}' is part of a cycle with no exit to an ending`, {
        path: `scenes.${sceneId}`,
        scene: sceneId,
      })
    );
  }

  return validationResult(
    errors,
    warnings,
    issues,
    stats(Object.keys(scenes).length, choiceCount, endingCount, reachable.size, unreachable.length)
  );
}

export function evaluateGuard(state, requires) {
  if (!requires || typeof requires !== "object" || Array.isArray(requires) || Object.keys(requires).length === 0) {
    return { passed: true, unmet: [] };
  }
  const unmet = [];
  for (const [key, minimum] of Object.entries(requires)) {
    const actual = state[key] === undefined ? 0 : state[key];
    const actualNum = numeric(actual);
    const minimumNum = numeric(minimum);
    if (actualNum === null || minimumNum === null || actualNum < minimumNum) {
      unmet.push({
        key: String(key),
        required: minimum,
        actual,
        reason: actualNum === null ? "non-numeric state value" : "below minimum",
      });
    }
  }
  return { passed: unmet.length === 0, unmet };
}

function asNumber(value) {
  return Number.isInteger(value) ? value : value;
}

export function applyEffects(state, effects) {
  if (effects === undefined || effects === null) return [];
  if (typeof effects !== "object" || Array.isArray(effects)) {
    throw new Error("effects must be an object");
  }
  const applied = [];
  for (const [rawKey, spec] of Object.entries(effects)) {
    const key = String(rawKey);
    if (spec && typeof spec === "object" && !Array.isArray(spec) && "op" in spec) {
      const op = String(spec.op).toLowerCase();
      const value = spec.value;
      if (op === "set") {
        state[key] = clone(value);
        applied.push({ key, op: "set", value, result: state[key] });
      } else if (op === "add") {
        const base = numeric(state[key] === undefined ? 0 : state[key]) ?? 0;
        const delta = numeric(value);
        if (delta === null) throw new Error(`effect '${key}': add requires a numeric value`);
        state[key] = asNumber(base + delta);
        applied.push({ key, op: "add", value, result: state[key] });
      } else if (op === "append") {
        let bucket = state[key];
        if (!Array.isArray(bucket)) bucket = bucket === undefined || bucket === null ? [] : [bucket];
        bucket.push(clone(value));
        state[key] = bucket;
        applied.push({ key, op: "append", value, result: state[key] });
      } else if (op === "delete") {
        delete state[key];
        applied.push({ key, op: "delete", result: null });
      } else {
        throw new Error(`effect '${key}': unknown op '${op}' (expected set|add|append|delete)`);
      }
    } else if (typeof spec === "number") {
      const base = numeric(state[key] === undefined ? 0 : state[key]) ?? 0;
      state[key] = asNumber(base + spec);
      applied.push({ key, op: "add", value: spec, result: state[key] });
    } else {
      state[key] = clone(spec);
      applied.push({ key, op: "set", value: spec, result: state[key] });
    }
  }
  return applied;
}

function resolveChoice(choiceList, rawChoice, sceneId) {
  if (typeof rawChoice === "boolean") {
    throw new Error("choice must be an integer index or label string, got boolean");
  }
  if (typeof rawChoice === "number") {
    if (!Number.isInteger(rawChoice)) throw new Error(`choice index ${rawChoice} must be an integer`);
    if (rawChoice < 0 || rawChoice >= choiceList.length) {
      throw new Error(
        `choice index ${rawChoice} out of range: scene '${sceneId}' has ${choiceList.length} choices`
      );
    }
    return rawChoice;
  }
  if (rawChoice && typeof rawChoice === "object") {
    if ("index" in rawChoice) return resolveChoice(choiceList, rawChoice.index, sceneId);
    if ("label" in rawChoice) return resolveChoice(choiceList, rawChoice.label, sceneId);
    throw new Error("choice object must contain 'index' or 'label'");
  }
  if (typeof rawChoice === "string") {
    const wanted = rawChoice.trim().toLowerCase();
    const matches = [];
    choiceList.forEach((choice, i) => {
      if (choice && typeof choice === "object" && String(choice.label ?? "").trim().toLowerCase() === wanted) {
        matches.push(i);
      }
    });
    if (!matches.length) throw new Error(`no choice labelled '${rawChoice}' in scene '${sceneId}'`);
    return matches[0];
  }
  throw new Error(`unsupported choice reference of type ${typeof rawChoice}`);
}

function coerceMemory(entries) {
  const memory = [];
  if (!Array.isArray(entries)) return memory;
  for (const entry of entries) {
    if (entry && typeof entry === "object" && "fact" in entry) {
      memory.push({ turn: Number(entry.turn ?? 0), fact: String(entry.fact) });
    } else if (typeof entry === "string" && entry.trim()) {
      memory.push({ turn: 0, fact: entry.trim() });
    }
  }
  return memory;
}

export function stepStoryState(story, choices, options = {}) {
  const normalized = normalizeStory(story);
  const scenes = normalized.scenes;

  const start = options.startScene || normalized.startScene;
  if (typeof start !== "string" || !(start in scenes)) {
    throw new Error(`start scene '${start}' is not defined in story.scenes`);
  }

  const currentState = Object.assign({}, clone(normalized.initialState) || {});
  if (options.state && typeof options.state === "object") {
    Object.assign(currentState, clone(options.state) || {});
  }

  const memoryLog = [...coerceMemory(options.memory), ...coerceMemory(options.remember)];

  if (!Array.isArray(choices)) throw new Error("choices must be an array of choice indexes or labels");

  let sceneId = start;
  const history = [sceneId];
  let turn = 0;
  const steps = [];
  let stoppedReason = null;

  if (choices.length === 0) {
    return stepResult(normalized, sceneId, currentState, memoryLog, history, steps, turn, "no_choices_supplied");
  }

  for (const rawChoice of choices) {
    const scene = scenes[sceneId];
    if (!scene || typeof scene !== "object") {
      stoppedReason = `scene '${sceneId}' is not defined`;
      break;
    }
    let choiceList = scene.choices || [];
    if (!Array.isArray(choiceList)) choiceList = [];

    const index = resolveChoice(choiceList, rawChoice, sceneId);
    const chosen = choiceList[index];
    if (!chosen || typeof chosen !== "object") {
      throw new Error(`choice #${index} in scene '${sceneId}' is malformed`);
    }

    const guardsEvaluated = [];
    choiceList.forEach((candidate, i) => {
      if (!candidate || typeof candidate !== "object") return;
      const { passed, unmet } = evaluateGuard(currentState, candidate.requires);
      guardsEvaluated.push({ choice_index: i, label: candidate.label ?? "", available: passed, unmet });
    });

    const { passed, unmet } = evaluateGuard(currentState, chosen.requires);
    const fired = passed
      ? Object.entries(chosen.requires || {}).map(([key, value]) => ({
          key: String(key),
          required: value,
          actual: currentState[key] === undefined ? 0 : currentState[key],
          satisfied: true,
        }))
      : [];

    const step = {
      turn: turn + 1,
      from_scene: sceneId,
      choice_index: index,
      choice_label: chosen.label ?? "",
      guards_evaluated: guardsEvaluated,
      fired_guards: fired,
      unmet_guards: unmet,
      status: passed ? "ok" : "guard_blocked",
    };

    if (!passed) {
      step.message = "guard predicate not satisfied; state unchanged";
      steps.push(step);
      stoppedReason = "guard_blocked";
      break;
    }

    step.effects_applied = applyEffects(currentState, chosen.effects || {});
    const next = chosen.next;
    turn += 1;
    step.to_scene = next;
    step.state = clone(currentState);
    step.memory = clone(memoryLog);
    steps.push(step);

    if (typeof next !== "string" || !(next in scenes)) {
      step.warning = `next scene '${next}' is not defined in story.scenes`;
      stoppedReason = "missing_target";
      break;
    }

    sceneId = next;
    history.push(next);
    if (scenes[next].ending === true) {
      stoppedReason = "ending_reached";
      break;
    }
  }

  if (stoppedReason === null) stoppedReason = "choices_exhausted";

  return stepResult(normalized, sceneId, currentState, memoryLog, history, steps, turn, stoppedReason);
}

function stepResult(normalized, sceneId, state, memory, history, steps, turn, stoppedReason) {
  const scenes = normalized.scenes;
  const scene = scenes[sceneId];
  const available = [];
  if (scene && typeof scene === "object") {
    (scene.choices || []).forEach((candidate, i) => {
      if (!candidate || typeof candidate !== "object") return;
      const { passed, unmet } = evaluateGuard(state, candidate.requires);
      available.push({
        choice_index: i,
        label: candidate.label ?? "",
        next: candidate.next,
        available: passed,
        unmet,
      });
    });
  }

  const tracePayload = {
    story_id: normalized.id,
    startScene: normalized.startScene,
    steps: steps.map((s) => ({
      turn: s.turn,
      from_scene: s.from_scene,
      to_scene: s.to_scene,
      state: s.state,
    })),
  };
  const traceHash = sha256Hex(canonicalJson(tracePayload));

  return {
    ok: true,
    story_id: normalized.id,
    start_scene: normalized.startScene,
    turns: turn,
    final_scene: sceneId,
    final_state: state,
    history,
    memory,
    memory_trace: memory,
    steps,
    available_choices: available,
    stopped_reason: stoppedReason,
    deterministic: true,
    trace_hash: traceHash,
    verification: {
      algorithm: "sha256",
      canonicalization: "JSON with sorted keys, no whitespace, integral floats as integers",
      payload: tracePayload,
      hash: traceHash,
      note:
        "Recompute sha256 over the canonical JSON of `payload`; a mismatch means the " +
        "story state was mutated outside this reducer (silent state drift).",
    },
  };
}

export const DRIFT_TAXONOMY = [
  {
    code: "F1",
    name: "Silent state loss",
    definition:
      "A previously established fact is dropped or contradicted with no signal to the reader; " +
      "local fluency and persona are preserved.",
    observed_instance:
      "Character.AI — 20 turns at ~3 s/reply, on-persona throughout, but the turn-15 query " +
      "returned a cafe menu and never produced 'Marmalade'.",
    detectable_from_transcript: true,
  },
  {
    code: "F2",
    name: "Session non-persistence",
    definition:
      "The reader's contributions do not survive the session: messages are accepted and then " +
      "absent on reload, or the model returns nothing at all.",
    observed_instance:
      "Janitor AI — clean email + 6-digit-code signup, but the free model returned 0 replies " +
      "across 4 sessions and sent messages did not persist after reload.",
    detectable_from_transcript: true,
  },
  {
    code: "F3",
    name: "Gating censoring",
    definition:
      "Progression halts before the probe can be administered, because of a signup wall, a " +
      "paid-trial wall, or an unreachable submission control.",
    observed_instance:
      "Talefy (7 s teaser, then reader signup + $9.99/7-day trial wall); Joyland (every chat " +
      "click opens a login modal); NovelAI (text signup submit unreachable in 6 attempts).",
    detectable_from_transcript: true,
  },
  {
    code: "F4",
    name: "Transient service degradation",
    definition:
      "Progression stalls mid-session for infrastructure reasons, then resumes. Recoverable, " +
      "and therefore not a capability failure.",
    observed_instance:
      "AI Dungeon — free-queue stall at turn 7; session resumed and passed the turn-15 probe " +
      "verbatim. Recorded as turns-before-wall = 7 without being scored as a wall.",
    detectable_from_transcript: true,
  },
  {
    code: "F5",
    name: "Platform delisting",
    definition:
      "The product disappears from its distribution channel, orphaning the reader's continuity " +
      "and any authored user content.",
    observed_instance:
      "Chai AI removed from the iOS App Store in October 2026; SpicyChat removed in late 2026 " +
      "(companion availability dataset, 10.5281/zenodo.24514920).",
    detectable_from_transcript: false,
  },
];

const VERDICTS = {
  PASS: {
    mode: "none",
    mode_code: "F0",
    label: "pass",
    drift_detected: false,
    passed: true,
    summary: "Planted fact was recalled at or after the probe turn with no contradiction.",
  },
  F4_TRANSIENT_DEGRADATION: {
    mode: "F4",
    mode_code: "F4",
    label: "transient_degradation",
    drift_detected: true,
    passed: true,
    summary: "Progression stalled after planting but recovered and recalled the fact.",
  },
  F1_CONTRADICTION: {
    mode: "F1",
    mode_code: "F1",
    label: "silent_state_loss_contradiction",
    drift_detected: true,
    passed: false,
    summary: "A later turn asserts a different value for the planted fact (contradiction).",
  },
  F1_OMISSION: {
    mode: "F1",
    mode_code: "F1",
    label: "silent_state_loss_omission",
    drift_detected: true,
    passed: false,
    summary: "The probe turn was reached but the planted fact was never recalled (omission).",
  },
  F2_SESSION_NON_PERSISTENCE: {
    mode: "F2",
    mode_code: "F2",
    label: "session_non_persistence",
    drift_detected: true,
    passed: false,
    summary: "Assistant turns after planting were empty (session did not persist).",
  },
  F3_GATING_CENSORING: {
    mode: "F3",
    mode_code: "F3",
    label: "right_censored",
    drift_detected: false,
    passed: null,
    summary: "The transcript stops before the probe turn; status is unknown rather than failed.",
  },
  F5_PLATFORM_DELISTING: {
    mode: "F5",
    mode_code: "F5",
    label: "untestable",
    drift_detected: false,
    passed: null,
    summary: "Platform delisting prevented the session from being administered at all.",
  },
  FACT_NOT_PLANTED: {
    mode: "unknown",
    mode_code: null,
    label: "not_planted",
    drift_detected: false,
    passed: null,
    summary: "The expected value never appears in the transcript, so no fact was planted.",
  },
  EMPTY_TRANSCRIPT: {
    mode: "unknown",
    mode_code: null,
    label: "empty_transcript",
    drift_detected: false,
    passed: null,
    summary: "The transcript contains no turns.",
  },
};

const norm = (text) => String(text).replace(/\s+/g, " ").trim().toLowerCase();
const contains = (text, needle) => {
  const n = norm(needle);
  return Boolean(n) && norm(text).includes(n);
};

export function normalizeTranscript(transcript) {
  if (!Array.isArray(transcript)) throw new Error("transcript must be an array of turns");
  return transcript.map((entry, i) => {
    if (typeof entry === "string") return { turn: i + 1, speaker: "unknown", text: entry };
    if (entry && typeof entry === "object") {
      const text = entry.text !== undefined ? entry.text : entry.content !== undefined ? entry.content : "";
      let number = Number(entry.turn === undefined ? i + 1 : entry.turn);
      if (!Number.isFinite(number)) number = i + 1;
      return { turn: number, speaker: String(entry.speaker ?? "unknown"), text: String(text ?? "") };
    }
    throw new Error(`transcript[${i}] must be a string or an object with a 'text' field`);
  });
}

function driftResult(verdict, fact, turns, plantedTurn, probe, recallTurns, contradictionTurns, emptyTurns, extra) {
  const spec = VERDICTS[verdict];
  const perTurn = turns.map((entry) => {
    let relation;
    if (plantedTurn !== null && entry.turn <= plantedTurn) relation = "at_or_before_planting";
    else if (!String(entry.text).trim()) relation = "empty";
    else if (recallTurns.includes(entry.turn)) relation = "recalled";
    else if (contradictionTurns.includes(entry.turn)) relation = "contradicted";
    else relation = "omitted";
    return { turn: entry.turn, speaker: entry.speaker, relation, text: entry.text };
  });

  const result = {
    ok: true,
    verdict,
    label: spec.label,
    mode: spec.mode,
    mode_code: spec.mode_code,
    drift_detected: spec.drift_detected,
    passed: spec.passed,
    summary: spec.summary,
    fact: { key: fact.key, expected_value: fact.expected_value, planted_turn: plantedTurn },
    probe_turn: probe,
    evidence: {
      turns_analyzed: turns.length,
      planted_turn: plantedTurn,
      probe_turn: probe,
      recall_turns: recallTurns,
      contradiction_turns: contradictionTurns,
      empty_turns: emptyTurns,
    },
    per_turn: perTurn,
    taxonomy: DRIFT_TAXONOMY,
    taxonomy_source: {
      title:
        "State Drift in Consumer LLM Interactive Fiction: A 15-Turn Empirical Benchmark " +
        "Across 10 Platforms and a 207-Line Deterministic Story-State Kernel",
      author: "Ouba Studio",
      year: 2026,
      doi: "10.5281/zenodo.24549412",
      url: "https://doi.org/10.5281/zenodo.24549412",
    },
    deterministic: true,
  };
  if (extra) Object.assign(result.evidence, extra);
  return result;
}

export function detectStateDrift(fact, transcript, options = {}) {
  if (!fact || typeof fact !== "object" || Array.isArray(fact)) {
    throw new Error("fact must be an object like {key, expected_value, planted_turn}");
  }
  if (fact.expected_value === undefined || fact.expected_value === null || !String(fact.expected_value).trim()) {
    throw new Error("fact.expected_value is required");
  }
  const expected = String(fact.expected_value).trim();
  const key = String(fact.key ?? "").trim();
  const wrongValues = (fact.wrong_values || []).map((v) => String(v)).filter((v) => v.trim());
  const aliases = (fact.aliases || []).map((a) => String(a)).filter((a) => a.trim());
  const contradictionMode = String(fact.contradiction_mode ?? "wrong_values").toLowerCase();
  const minGap = Number.isInteger(options.minGap) && options.minGap >= 1 ? options.minGap : 2;

  const turns = normalizeTranscript(transcript);
  if (!turns.length) {
    return driftResult("EMPTY_TRANSCRIPT", fact, turns, null, null, [], [], []);
  }

  const maxTurn = Math.max(...turns.map((t) => t.turn));
  let plantedTurn = fact.planted_turn;
  if (plantedTurn !== undefined && plantedTurn !== null) {
    plantedTurn = Number(plantedTurn);
    if (!Number.isInteger(plantedTurn)) throw new Error("fact.planted_turn must be an integer");
  } else {
    plantedTurn = null;
    for (const entry of turns) {
      if (contains(entry.text, expected) || aliases.some((a) => contains(entry.text, a))) {
        plantedTurn = entry.turn;
        break;
      }
    }
  }

  if (plantedTurn === null) {
    return driftResult("FACT_NOT_PLANTED", fact, turns, null, null, [], [], []);
  }

  // Even when the caller supplies planted_turn, the fact must actually appear in
  // the transcript — otherwise the premise is false and no verdict is meaningful.
  const plantedPresent = turns.some(
    (entry) => contains(entry.text, expected) || aliases.some((a) => contains(entry.text, a))
  );
  if (!plantedPresent) {
    return driftResult("FACT_NOT_PLANTED", fact, turns, null, null, [], [], []);
  }

  const probeExplicit = options.probeTurn !== undefined && options.probeTurn !== null;
  const probe = probeExplicit ? Number(options.probeTurn) : maxTurn;
  if (!Number.isInteger(probe)) throw new Error("probe_turn must be an integer");

  const postPlant = turns.filter((t) => t.turn > plantedTurn);

  const recallTurns = postPlant
    .filter((t) => contains(t.text, expected) || aliases.some((a) => contains(t.text, a)))
    .map((t) => t.turn);

  const contradictionTurns = [];
  for (const entry of postPlant) {
    let contradicted = wrongValues.some((wrong) => contains(entry.text, wrong));
    if (!contradicted && contradictionMode === "key_mention_without_value" && key) {
      contradicted = contains(entry.text, key) && !contains(entry.text, expected);
    }
    if (contradicted) contradictionTurns.push(entry.turn);
  }

  const emptyTurns = postPlant.filter((t) => !String(t.text).trim()).map((t) => t.turn);
  const recallAtProbe = recallTurns.filter((t) => t >= probe);
  const contradictionAfterPlant = [...contradictionTurns];

  let stall = false;
  if (recallAtProbe.length) {
    const firstRecall = Math.min(...recallAtProbe);
    const present = new Set(
      postPlant.filter((t) => plantedTurn < t.turn && t.turn <= firstRecall).map((t) => t.turn)
    );
    const missing = [];
    for (let n = plantedTurn + 1; n <= firstRecall; n += 1) if (!present.has(n)) missing.push(n);
    stall =
      Boolean(emptyTurns.filter((t) => plantedTurn < t && t <= firstRecall).length) || Boolean(missing.length);
  } else {
    stall = Boolean(emptyTurns.length);
  }

  if (!stall) {
    let previous = null;
    for (const entry of postPlant) {
      const text = norm(entry.text);
      if (text && text === previous) {
        stall = true;
        break;
      }
      previous = text || previous;
    }
  }

  const reachedProbe = probeExplicit ? maxTurn >= probe : maxTurn >= plantedTurn + Math.max(1, minGap);

  let verdict;
  if (options.delisted) verdict = "F5_PLATFORM_DELISTING";
  else if (contradictionAfterPlant.length) verdict = "F1_CONTRADICTION";
  else if (recallAtProbe.length && stall) verdict = "F4_TRANSIENT_DEGRADATION";
  else if (recallAtProbe.length) verdict = "PASS";
  else if (!reachedProbe) verdict = "F3_GATING_CENSORING";
  else if (emptyTurns.length) verdict = "F2_SESSION_NON_PERSISTENCE";
  else verdict = "F1_OMISSION";

  return driftResult(verdict, fact, turns, plantedTurn, probe, recallTurns, contradictionTurns, emptyTurns, {
    stall_detected: stall,
    probe_reached: reachedProbe,
    last_turn: maxTurn,
  });
}
