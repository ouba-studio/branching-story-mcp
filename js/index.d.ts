/**
 * TypeScript declarations for branching-story-mcp (zero-dependency ESM mirror).
 * MIT License — Ouba Studio <team@ouba.art> — https://www.ouba.art/
 */

export interface StoryChoice {
  label: string;
  next?: string;
  href?: string;
  requires?: Record<string, number>;
  effects?: Record<string, number | string | boolean | null | EffectOp>;
}

export interface EffectOp {
  op: "set" | "add" | "append" | "delete";
  value?: unknown;
}

export interface StoryScene {
  title: string;
  body: string;
  choices?: StoryChoice[];
  ending?: boolean;
}

export interface StoryGraph {
  id?: string;
  title?: string;
  startScene?: string;
  start?: string;
  initialState?: Record<string, unknown>;
  scenes: Record<string, StoryScene>;
}

export interface Issue {
  code: string;
  message: string;
  path?: string;
  scene?: string;
  [key: string]: unknown;
}

export interface ValidationIssueBuckets {
  missing_targets: Array<Record<string, unknown>>;
  unreachable_scenes: Array<{ scene: string }>;
  dead_ends: Array<{ scene: string }>;
  loop_traps: Array<{ scene: string }>;
  invalid_guards: Array<Record<string, unknown>>;
}

export interface ValidationResult {
  valid: boolean;
  error_count: number;
  warning_count: number;
  errors: Issue[];
  warnings: Issue[];
  issues: ValidationIssueBuckets;
  stats: {
    scenes: number;
    choices: number;
    endings: number;
    reachable_scenes: number;
    unreachable_scenes: number;
  };
}

export interface GuardEvaluation {
  choice_index: number;
  label: string;
  available: boolean;
  unmet: Array<{ key: string; required: number; actual: unknown; reason: string }>;
}

export interface StepRecord {
  turn: number;
  from_scene: string;
  choice_index: number;
  choice_label: string;
  guards_evaluated: GuardEvaluation[];
  fired_guards: Array<{ key: string; required: number; actual: unknown; satisfied: boolean }>;
  unmet_guards: Array<{ key: string; required: number; actual: unknown; reason: string }>;
  status: "ok" | "guard_blocked";
  message?: string;
  effects_applied?: Array<{ key: string; op: string; value?: unknown; result: unknown }>;
  to_scene?: string;
  state?: Record<string, unknown>;
  memory?: MemoryEntry[];
  warning?: string;
}

export interface MemoryEntry {
  turn: number;
  fact: string;
}

export interface StepResult {
  ok: true;
  story_id?: string;
  start_scene: string;
  turns: number;
  final_scene: string;
  final_state: Record<string, unknown>;
  history: string[];
  memory: MemoryEntry[];
  memory_trace: MemoryEntry[];
  steps: StepRecord[];
  available_choices: GuardEvaluation[];
  stopped_reason: string;
  deterministic: true;
  trace_hash: string;
  verification: {
    algorithm: "sha256";
    canonicalization: string;
    payload: unknown;
    hash: string;
    note: string;
  };
}

export interface DriftFact {
  key: string;
  expected_value: string;
  planted_turn?: number;
  wrong_values?: string[];
  aliases?: string[];
  contradiction_mode?: "wrong_values" | "key_mention_without_value";
}

export interface DriftResult {
  ok: true;
  verdict: string;
  label: string;
  mode: string;
  mode_code: string | null;
  drift_detected: boolean;
  passed: boolean | null;
  summary: string;
  fact: { key: string; expected_value: string; planted_turn: number | null };
  probe_turn: number | null;
  evidence: Record<string, unknown>;
  per_turn: Array<{ turn: number; speaker: string; relation: string; text: string }>;
  taxonomy: Array<{ code: string; name: string; definition: string; observed_instance: string }>;
  taxonomy_source: { title: string; author: string; year: number; doi: string; url: string };
  deterministic: true;
}

export interface BenchmarkCitation {
  apa: string;
  bibtex: string;
  doi: string;
  doi_url: string;
  license: string;
  license_url: string;
  explorer_url: string;
  taxonomy_doi: string;
  taxonomy_url: string;
}

export const VERSION: string;
export const SERVER_NAME: string;
export const DATASET_DOI: string;
export const EXPLORER_URL: string;
export const TAXONOMY_DOI: string;
export const BENCHMARK: Record<string, unknown>;
export const STORY_GRAPH_SCHEMA: Record<string, unknown>;
export const DRIFT_TAXONOMY: Array<{ code: string; name: string }>;

export function canonicalJson(value: unknown): string;
export function sha256Hex(text: string): string;
export function normalizeStory(raw: unknown): StoryGraph;
export function validateStoryGraph(story: unknown): ValidationResult;
export function evaluateGuard(
  state: Record<string, unknown>,
  requires?: Record<string, number>
): { passed: boolean; unmet: Array<{ key: string; required: number; actual: unknown; reason: string }> };
export function applyEffects(
  state: Record<string, unknown>,
  effects?: Record<string, unknown>
): Array<{ key: string; op: string; value?: unknown; result: unknown }>;
export function stepStoryState(
  story: StoryGraph,
  choices: Array<number | string | { index?: number; label?: string }>,
  options?: {
    state?: Record<string, unknown>;
    memory?: Array<string | MemoryEntry>;
    remember?: Array<string | MemoryEntry>;
    startScene?: string;
  }
): StepResult;
export function detectStateDrift(
  fact: DriftFact,
  transcript: Array<string | { turn?: number; speaker?: string; text: string }>,
  options?: { probeTurn?: number; minGap?: number; delisted?: boolean }
): DriftResult;
export function queryBenchmark(options?: { platform?: string; status?: string }): Record<string, unknown>;
export function benchmarkCitation(): BenchmarkCitation;

export const TOOLS: Array<Record<string, unknown>>;
export const RESOURCES: Array<Record<string, unknown>>;
export const SERVER_INFO: { name: string; version: string };
export function handleMessage(message: unknown): unknown;
export function main(): Promise<number>;
