"""Deterministic story-state kernel for branching-story-mcp.

This module is a pure-stdlib re-implementation of the ``branching-story-kit``
v1.0.0 engine, extended with the explicit ``set`` / ``add`` / ``append`` effect
operators and the five-mode silent-state-drift taxonomy published in
"State Drift in Consumer LLM Interactive Fiction" (doi:10.5281/zenodo.24549412).

Everything in here is deterministic: identical inputs always produce identical
outputs *and* an identical ``trace_hash`` in both the Python and the JavaScript
implementations, so an agent can verify that no silent state drift occurred.

No third-party imports. Python >= 3.10.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

__all__ = [
    "VERSION",
    "SERVER_NAME",
    "canonical_json",
    "sha256_hex",
    "normalize_story",
    "validate_story_graph",
    "evaluate_guard",
    "apply_effects",
    "step_story_state",
    "detect_state_drift",
    "STORY_GRAPH_SCHEMA",
    "DRIFT_TAXONOMY",
]

VERSION = "1.0.0"
SERVER_NAME = "branching-story-mcp"

# ---------------------------------------------------------------------------
# Canonical JSON + hashing (identical byte-for-byte in the JS mirror)
# ---------------------------------------------------------------------------


def _normalize_numbers(value: Any) -> Any:
    """Collapse integral floats to ints so Python and JS hash identically."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        return {str(k): _normalize_numbers(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_numbers(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no spaces, integral floats as ints."""
    return json.dumps(
        _normalize_numbers(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Story graph schema (branching-story-kit v1, start/startScene alias)
# ---------------------------------------------------------------------------

STORY_GRAPH_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "ouba://schema/story-graph-v1",
    "title": "branching-story-kit story graph v1",
    "type": "object",
    "required": ["scenes", "startScene"],
    "properties": {
        "id": {"type": "string", "description": "Stable story identifier."},
        "title": {"type": "string", "description": "Human-readable story title."},
        "startScene": {
            "type": "string",
            "description": "Scene id the reader enters first. The legacy alias `start` is accepted.",
        },
        "start": {"type": "string", "description": "Legacy alias for startScene."},
        "initialState": {
            "type": "object",
            "description": "Initial story-state vector (relationship meters, flags, inventory).",
            "additionalProperties": {"type": ["number", "string", "boolean", "array", "null"]},
        },
        "scenes": {
            "type": "object",
            "description": "Map of scene id -> scene definition.",
            "additionalProperties": {"$ref": "#/$defs/scene"},
        },
    },
    "$defs": {
        "scene": {
            "type": "object",
            "required": ["title", "body"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string", "description": "Scene prose. `{{key}}` interpolates state."},
                "ending": {"type": "boolean", "default": False},
                "choices": {"type": "array", "items": {"$ref": "#/$defs/choice"}},
            },
        },
        "choice": {
            "type": "object",
            "required": ["label"],
            "properties": {
                "label": {"type": "string"},
                "next": {"type": "string", "description": "Target scene id."},
                "href": {"type": "string", "description": "External link target (no state change)."},
                "requires": {
                    "type": "object",
                    "description": "Guard predicate: state key -> minimum numeric value.",
                    "additionalProperties": {"type": "number"},
                },
                "effects": {
                    "type": "object",
                    "description": (
                        "State mutations. Scalar numbers add, strings/booleans assign, and "
                        "{op: set|add|append|delete, value} gives explicit control."
                    ),
                    "additionalProperties": True,
                },
            },
        },
        "effectOp": {
            "type": "object",
            "required": ["op"],
            "properties": {
                "op": {"type": "string", "enum": ["set", "add", "append", "delete"]},
                "value": {},
            },
        },
    },
}


def normalize_story(raw: Any) -> dict[str, Any]:
    """Return a canonical story dict or raise ``ValueError`` when unusable."""
    if not isinstance(raw, dict):
        raise ValueError("story must be a JSON object")
    scenes = raw.get("scenes")
    if not isinstance(scenes, dict) or not scenes:
        raise ValueError("story.scenes must be a non-empty object")
    start = raw.get("startScene") or raw.get("start")
    initial = raw.get("initialState")
    if initial is not None and not isinstance(initial, dict):
        raise ValueError("story.initialState must be an object when present")
    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "startScene": start,
        "initialState": dict(initial or {}),
        "scenes": scenes,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _issue(code: str, message: str, **extra: Any) -> dict[str, Any]:
    issue: dict[str, Any] = {"code": code, "message": message}
    issue.update(extra)
    return issue


def _effect_keys(scenes: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for scene in scenes.values():
        if not isinstance(scene, dict):
            continue
        for choice in scene.get("choices") or []:
            if isinstance(choice, dict) and isinstance(choice.get("effects"), dict):
                keys.update(str(k) for k in choice["effects"].keys())
    return keys


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def validate_story_graph(story: Any) -> dict[str, Any]:
    """Validate a story graph and return structured diagnostics.

    Severity model: ``errors`` make ``valid`` false; ``warnings`` do not.
    Missing targets, malformed schema and non-numeric guards are errors.
    Unreachable scenes, dead ends, loop traps and unknown guard keys are
    warnings (they are real authoring smells but do not break the runtime).
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    issues: dict[str, list[dict[str, Any]]] = {
        "missing_targets": [],
        "unreachable_scenes": [],
        "dead_ends": [],
        "loop_traps": [],
        "invalid_guards": [],
    }

    if not isinstance(story, dict):
        return _validation_result(
            errors=[_issue("SCHEMA_INVALID_STORY", "story must be a JSON object", path="story")],
            warnings=[],
            issues=issues,
            stats=_stats(0, 0, 0, 0, 0),
        )

    scenes = story.get("scenes")
    if not isinstance(scenes, dict) or not scenes:
        return _validation_result(
            errors=[_issue("SCHEMA_MISSING_SCENES", "story.scenes must be a non-empty object", path="scenes")],
            warnings=[],
            issues=issues,
            stats=_stats(0, 0, 0, 0, 0),
        )

    start = story.get("startScene") or story.get("start")
    if not isinstance(start, str) or not start.strip():
        errors.append(_issue("SCHEMA_MISSING_START", "story.startScene (or legacy story.start) is required", path="startScene"))
    elif start not in scenes:
        errors.append(
            _issue(
                "SCHEMA_START_NOT_FOUND",
                f"start scene '{start}' is not defined in story.scenes",
                path="startScene",
                scene=start,
            )
        )

    initial = story.get("initialState")
    if initial is None:
        initial = {}
    if not isinstance(initial, dict):
        errors.append(_issue("SCHEMA_INVALID_INITIAL_STATE", "story.initialState must be an object", path="initialState"))
        initial = {}

    produced = _effect_keys(scenes)
    known_state_keys = {str(k) for k in initial.keys()} | produced

    choice_count = 0
    ending_count = 0
    edges: dict[str, list[str]] = {}

    for scene_id, scene in scenes.items():
        if not isinstance(scene, dict):
            errors.append(
                _issue("SCHEMA_INVALID_SCENE", f"scene '{scene_id}' must be an object", path=f"scenes.{scene_id}")
            )
            continue

        title = scene.get("title")
        if not isinstance(title, str) or not title.strip():
            warnings.append(
                _issue("SCENE_MISSING_TITLE", f"scene '{scene_id}' has no title", path=f"scenes.{scene_id}.title")
            )
        body = scene.get("body")
        if not isinstance(body, str) or not body.strip():
            warnings.append(
                _issue("SCENE_MISSING_BODY", f"scene '{scene_id}' has no body prose", path=f"scenes.{scene_id}.body")
            )
        if not isinstance(scene.get("ending", False), bool):
            errors.append(
                _issue(
                    "SCENE_INVALID_ENDING",
                    f"scene '{scene_id}'.ending must be a boolean",
                    path=f"scenes.{scene_id}.ending",
                )
            )
        if scene.get("ending") is True:
            ending_count += 1

        choices = scene.get("choices")
        if choices is None:
            choices = []
        if not isinstance(choices, list):
            errors.append(
                _issue(
                    "SCENE_INVALID_CHOICES",
                    f"scene '{scene_id}'.choices must be an array",
                    path=f"scenes.{scene_id}.choices",
                )
            )
            choices = []

        outgoing: list[str] = []
        for index, choice in enumerate(choices):
            if not isinstance(choice, dict):
                errors.append(
                    _issue(
                        "SCHEMA_INVALID_CHOICE",
                        f"scene '{scene_id}' choice #{index} must be an object",
                        path=f"scenes.{scene_id}.choices[{index}]",
                    )
                )
                continue
            choice_count += 1
            label = choice.get("label", "")

            nxt = choice.get("next")
            href = choice.get("href")
            if not isinstance(nxt, str) or not nxt:
                if not isinstance(href, str) or not href:
                    errors.append(
                        _issue(
                            "SCHEMA_CHOICE_NO_TARGET",
                            f"scene '{scene_id}' choice #{index} ('{label}') needs a 'next' scene id or an 'href'",
                            path=f"scenes.{scene_id}.choices[{index}]",
                        )
                    )
                continue

            if nxt not in scenes:
                record = {
                    "scene": scene_id,
                    "choice_index": index,
                    "label": label,
                    "next": nxt,
                }
                issues["missing_targets"].append(record)
                errors.append(
                    _issue(
                        "MISSING_TARGET",
                        f"scene '{scene_id}' choice #{index} links to missing scene '{nxt}'",
                        path=f"scenes.{scene_id}.choices[{index}].next",
                        **record,
                    )
                )
            else:
                outgoing.append(nxt)

            requires = choice.get("requires")
            if requires is not None:
                if not isinstance(requires, dict):
                    record = {
                        "scene": scene_id,
                        "choice_index": index,
                        "label": label,
                        "reason": "requires must be an object mapping state keys to numeric minimums",
                    }
                    issues["invalid_guards"].append(record)
                    errors.append(
                        _issue(
                            "INVALID_GUARD",
                            f"scene '{scene_id}' choice #{index} has a non-object 'requires' guard",
                            path=f"scenes.{scene_id}.choices[{index}].requires",
                            **record,
                        )
                    )
                else:
                    for key, minimum in requires.items():
                        if _numeric(minimum) is None:
                            record = {
                                "scene": scene_id,
                                "choice_index": index,
                                "label": label,
                                "key": str(key),
                                "reason": f"requirement for '{key}' must be a number",
                            }
                            issues["invalid_guards"].append(record)
                            errors.append(
                                _issue(
                                    "INVALID_GUARD",
                                    f"scene '{scene_id}' choice #{index} guard for '{key}' is not numeric",
                                    path=f"scenes.{scene_id}.choices[{index}].requires.{key}",
                                    **record,
                                )
                            )
                        elif str(key) not in known_state_keys:
                            record = {
                                "scene": scene_id,
                                "choice_index": index,
                                "label": label,
                                "key": str(key),
                                "reason": f"guard references unknown state key '{key}'",
                            }
                            issues["invalid_guards"].append(record)
                            warnings.append(
                                _issue(
                                    "INVALID_GUARD_UNKNOWN_KEY",
                                    f"scene '{scene_id}' choice #{index} guards on undeclared state key '{key}'",
                                    path=f"scenes.{scene_id}.choices[{index}].requires.{key}",
                                    **record,
                                )
                            )

            effects = choice.get("effects")
            if effects is not None and not isinstance(effects, dict):
                errors.append(
                    _issue(
                        "SCHEMA_INVALID_EFFECTS",
                        f"scene '{scene_id}' choice #{index} has a non-object 'effects' value",
                        path=f"scenes.{scene_id}.choices[{index}].effects",
                    )
                )

        edges[scene_id] = outgoing

    # Reachability from the start scene.
    reachable: set[str] = set()
    if isinstance(start, str) and start in scenes:
        stack = [start]
        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)
            stack.extend(edges.get(node, []))
    unreachable = sorted(str(s) for s in scenes if s not in reachable) if reachable else []
    for scene_id in unreachable:
        issues["unreachable_scenes"].append({"scene": scene_id})
        warnings.append(
            _issue(
                "UNREACHABLE_SCENE",
                f"scene '{scene_id}' cannot be reached from the start scene",
                path=f"scenes.{scene_id}",
                scene=scene_id,
            )
        )

    # Dead ends: non-ending scenes with no outgoing choices at all.
    for scene_id, scene in scenes.items():
        if not isinstance(scene, dict):
            continue
        if scene.get("ending") is True:
            continue
        if not edges.get(scene_id) and not scene.get("choices"):
            issues["dead_ends"].append({"scene": scene_id})
            warnings.append(
                _issue(
                    "DEAD_END",
                    f"scene '{scene_id}' is not marked ending and has no choices",
                    path=f"scenes.{scene_id}",
                    scene=scene_id,
                )
            )

    # Loop traps: reachable cycles with no path to any terminal scene.
    terminals = {
        sid
        for sid, scene in scenes.items()
        if isinstance(scene, dict) and (scene.get("ending") is True or not edges.get(sid))
    }
    can_exit = set(terminals)
    changed = True
    while changed:
        changed = False
        for sid in scenes:
            if sid in can_exit:
                continue
            if any(node in can_exit for node in edges.get(sid, [])):
                can_exit.add(sid)
                changed = True
    for scene_id in sorted(str(s) for s in reachable if s not in can_exit):
        issues["loop_traps"].append({"scene": scene_id})
        warnings.append(
            _issue(
                "LOOP_TRAP",
                f"scene '{scene_id}' is part of a cycle with no exit to an ending",
                path=f"scenes.{scene_id}",
                scene=scene_id,
            )
        )

    stats = _stats(
        len(scenes),
        choice_count,
        ending_count,
        len(reachable),
        len(unreachable),
    )
    return _validation_result(errors=errors, warnings=warnings, issues=issues, stats=stats)


def _stats(scenes: int, choices: int, endings: int, reachable: int, unreachable: int) -> dict[str, int]:
    return {
        "scenes": scenes,
        "choices": choices,
        "endings": endings,
        "reachable_scenes": reachable,
        "unreachable_scenes": unreachable,
    }


def _validation_result(
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    issues: dict[str, list[dict[str, Any]]],
    stats: dict[str, int],
) -> dict[str, Any]:
    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "issues": issues,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# Guards + effects (the single write path)
# ---------------------------------------------------------------------------


def evaluate_guard(state: dict[str, Any], requires: Any) -> tuple[bool, list[dict[str, Any]]]:
    """Evaluate a ``requires`` predicate: every key must be >= its minimum."""
    if not isinstance(requires, dict) or not requires:
        return True, []
    unmet: list[dict[str, Any]] = []
    for key, minimum in requires.items():
        actual = state.get(key, 0)
        actual_num = _numeric(actual)
        minimum_num = _numeric(minimum)
        if actual_num is None or minimum_num is None or actual_num < minimum_num:
            unmet.append(
                {
                    "key": str(key),
                    "required": minimum,
                    "actual": actual,
                    "reason": "non-numeric state value" if actual_num is None else "below minimum",
                }
            )
    return len(unmet) == 0, unmet


def apply_effects(state: dict[str, Any], effects: Any) -> list[dict[str, Any]]:
    """Apply effects in place and return an audit trail.

    Legacy scalar semantics from branching-story-kit v1.0.0:
      * numbers  -> add to the current value
      * everything else -> assign
    Explicit operator objects give full control:
      * {"op": "set", "value": x}
      * {"op": "add", "value": n}
      * {"op": "append", "value": x}
      * {"op": "delete"}
    """
    if effects is None:
        return []
    if not isinstance(effects, dict):
        raise ValueError("effects must be an object")
    applied: list[dict[str, Any]] = []
    for raw_key, spec in effects.items():
        key = str(raw_key)
        if isinstance(spec, dict) and "op" in spec:
            op = str(spec.get("op")).lower()
            value = spec.get("value")
            if op == "set":
                state[key] = copy.deepcopy(value)
                applied.append({"key": key, "op": "set", "value": value, "result": state[key]})
            elif op == "add":
                base = _numeric(state.get(key, 0)) or 0.0
                delta = _numeric(value)
                if delta is None:
                    raise ValueError(f"effect '{key}': add requires a numeric value")
                state[key] = _as_number(base + delta)
                applied.append({"key": key, "op": "add", "value": value, "result": state[key]})
            elif op == "append":
                bucket = state.get(key)
                if not isinstance(bucket, list):
                    bucket = [] if bucket is None else [bucket]
                bucket.append(copy.deepcopy(value))
                state[key] = bucket
                applied.append({"key": key, "op": "append", "value": value, "result": state[key]})
            elif op == "delete":
                state.pop(key, None)
                applied.append({"key": key, "op": "delete", "result": None})
            else:
                raise ValueError(f"effect '{key}': unknown op '{op}' (expected set|add|append|delete)")
        elif isinstance(spec, bool) or spec is None or isinstance(spec, (str, list, dict)):
            state[key] = copy.deepcopy(spec)
            applied.append({"key": key, "op": "set", "value": spec, "result": state[key]})
        elif isinstance(spec, (int, float)):
            base = _numeric(state.get(key, 0)) or 0.0
            state[key] = _as_number(base + float(spec))
            applied.append({"key": key, "op": "add", "value": spec, "result": state[key]})
        else:
            state[key] = spec
            applied.append({"key": key, "op": "set", "value": spec, "result": state[key]})
    return applied


def _as_number(value: float) -> Any:
    return int(value) if float(value).is_integer() else value


# ---------------------------------------------------------------------------
# Stepping
# ---------------------------------------------------------------------------


def _resolve_choice(choice_list: list[Any], raw_choice: Any, scene_id: str) -> int:
    if isinstance(raw_choice, bool):
        raise ValueError(f"choice must be an integer index or label string, got boolean")
    if isinstance(raw_choice, (int, float)):
        if isinstance(raw_choice, float) and not raw_choice.is_integer():
            raise ValueError(f"choice index {raw_choice} must be an integer")
        index = int(raw_choice)
        if index < 0 or index >= len(choice_list):
            raise ValueError(
                f"choice index {index} out of range: scene '{scene_id}' has {len(choice_list)} choices"
            )
        return index
    if isinstance(raw_choice, dict):
        if "index" in raw_choice:
            return _resolve_choice(choice_list, raw_choice["index"], scene_id)
        if "label" in raw_choice:
            return _resolve_choice(choice_list, raw_choice["label"], scene_id)
        raise ValueError("choice object must contain 'index' or 'label'")
    if isinstance(raw_choice, str):
        wanted = raw_choice.strip().lower()
        matches = [
            i
            for i, choice in enumerate(choice_list)
            if isinstance(choice, dict) and str(choice.get("label", "")).strip().lower() == wanted
        ]
        if not matches:
            raise ValueError(f"no choice labelled {raw_choice!r} in scene '{scene_id}'")
        return matches[0]
    raise ValueError(f"unsupported choice reference of type {type(raw_choice).__name__}")


def _coerce_memory(entries: Any) -> list[dict[str, Any]]:
    memory: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        return memory
    for entry in entries:
        if isinstance(entry, dict) and "fact" in entry:
            memory.append({"turn": int(entry.get("turn", 0)), "fact": str(entry["fact"])})
        elif isinstance(entry, str) and entry.strip():
            memory.append({"turn": 0, "fact": entry.strip()})
    return memory


def step_story_state(
    story: Any,
    choices: Any,
    state: dict[str, Any] | None = None,
    memory: list[Any] | None = None,
    remember: list[Any] | None = None,
    start_scene: str | None = None,
) -> dict[str, Any]:
    """Run the deterministic reducer over one or more player choices."""
    normalized = normalize_story(story)
    scenes = normalized["scenes"]

    start = start_scene or normalized["startScene"]
    if not isinstance(start, str) or start not in scenes:
        raise ValueError(f"start scene {start!r} is not defined in story.scenes")

    current_state: dict[str, Any] = copy.deepcopy(normalized["initialState"])
    if isinstance(state, dict):
        current_state.update(copy.deepcopy(state))

    memory_log = _coerce_memory(memory) + _coerce_memory(remember)

    scene_id = start
    history: list[str] = [scene_id]
    turn = 0
    steps: list[dict[str, Any]] = []
    stopped_reason: str | None = None

    if not isinstance(choices, list):
        raise ValueError("choices must be an array of choice indexes or labels")
    if not choices:
        return _step_result(
            normalized=normalized,
            scene_id=scene_id,
            state=current_state,
            memory=memory_log,
            history=history,
            steps=steps,
            turn=turn,
            stopped_reason="no_choices_supplied",
        )

    for raw_choice in choices:
        scene = scenes.get(scene_id)
        if not isinstance(scene, dict):
            stopped_reason = f"scene '{scene_id}' is not defined"
            break
        choice_list = scene.get("choices") or []
        if not isinstance(choice_list, list):
            choice_list = []

        index = _resolve_choice(choice_list, raw_choice, scene_id)
        chosen = choice_list[index]
        if not isinstance(chosen, dict):
            raise ValueError(f"choice #{index} in scene '{scene_id}' is malformed")

        guards_evaluated = []
        for i, candidate in enumerate(choice_list):
            if not isinstance(candidate, dict):
                continue
            passed, unmet = evaluate_guard(current_state, candidate.get("requires"))
            guards_evaluated.append(
                {
                    "choice_index": i,
                    "label": candidate.get("label", ""),
                    "available": passed,
                    "unmet": unmet,
                }
            )

        passed, unmet = evaluate_guard(current_state, chosen.get("requires"))
        fired = (
            [
                {"key": str(k), "required": v, "actual": current_state.get(k, 0), "satisfied": True}
                for k, v in (chosen.get("requires") or {}).items()
            ]
            if passed
            else []
        )

        step: dict[str, Any] = {
            "turn": turn + 1,
            "from_scene": scene_id,
            "choice_index": index,
            "choice_label": chosen.get("label", ""),
            "guards_evaluated": guards_evaluated,
            "fired_guards": fired,
            "unmet_guards": unmet,
            "status": "ok" if passed else "guard_blocked",
        }

        if not passed:
            step["message"] = "guard predicate not satisfied; state unchanged"
            steps.append(step)
            stopped_reason = "guard_blocked"
            break

        step["effects_applied"] = apply_effects(current_state, chosen.get("effects") or {})
        nxt = chosen.get("next")
        turn += 1
        step["to_scene"] = nxt
        step["state"] = copy.deepcopy(current_state)
        step["memory"] = copy.deepcopy(memory_log)
        steps.append(step)

        if not isinstance(nxt, str) or nxt not in scenes:
            step["warning"] = f"next scene '{nxt}' is not defined in story.scenes"
            stopped_reason = "missing_target"
            break

        scene_id = nxt
        history.append(nxt)
        if scenes[nxt].get("ending") is True:
            stopped_reason = "ending_reached"
            break
    else:
        stopped_reason = stopped_reason or "choices_exhausted"

    if stopped_reason is None:
        stopped_reason = "choices_exhausted"

    return _step_result(
        normalized=normalized,
        scene_id=scene_id,
        state=current_state,
        memory=memory_log,
        history=history,
        steps=steps,
        turn=turn,
        stopped_reason=stopped_reason,
    )


def _step_result(
    normalized: dict[str, Any],
    scene_id: str,
    state: dict[str, Any],
    memory: list[dict[str, Any]],
    history: list[str],
    steps: list[dict[str, Any]],
    turn: int,
    stopped_reason: str | None,
) -> dict[str, Any]:
    scenes = normalized["scenes"]
    scene = scenes.get(scene_id) if isinstance(scene_id, str) else None
    available = []
    if isinstance(scene, dict):
        for i, candidate in enumerate(scene.get("choices") or []):
            if not isinstance(candidate, dict):
                continue
            passed, unmet = evaluate_guard(state, candidate.get("requires"))
            available.append(
                {
                    "choice_index": i,
                    "label": candidate.get("label", ""),
                    "next": candidate.get("next"),
                    "available": passed,
                    "unmet": unmet,
                }
            )

    trace_payload = {
        "story_id": normalized.get("id"),
        "startScene": normalized["startScene"],
        "steps": [
            {
                "turn": s["turn"],
                "from_scene": s["from_scene"],
                "to_scene": s.get("to_scene"),
                "state": s.get("state"),
            }
            for s in steps
        ],
    }
    trace_hash = sha256_hex(canonical_json(trace_payload))

    return {
        "ok": True,
        "story_id": normalized.get("id"),
        "start_scene": normalized["startScene"],
        "turns": turn,
        "final_scene": scene_id,
        "final_state": state,
        "history": history,
        "memory": memory,
        "memory_trace": memory,
        "steps": steps,
        "available_choices": available,
        "stopped_reason": stopped_reason,
        "deterministic": True,
        "trace_hash": trace_hash,
        "verification": {
            "algorithm": "sha256",
            "canonicalization": "JSON with sorted keys, no whitespace, integral floats as integers",
            "payload": trace_payload,
            "hash": trace_hash,
            "note": (
                "Recompute sha256 over the canonical JSON of `payload`; a mismatch means the "
                "story state was mutated outside this reducer (silent state drift)."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Silent state drift detection (five-mode taxonomy)
# ---------------------------------------------------------------------------

DRIFT_TAXONOMY: list[dict[str, Any]] = [
    {
        "code": "F1",
        "name": "Silent state loss",
        "definition": (
            "A previously established fact is dropped or contradicted with no signal to the "
            "reader; local fluency and persona are preserved."
        ),
        "observed_instance": (
            "Character.AI — 20 turns at ~3 s/reply, on-persona throughout, but the turn-15 "
            "query returned a cafe menu and never produced 'Marmalade'."
        ),
        "detectable_from_transcript": True,
    },
    {
        "code": "F2",
        "name": "Session non-persistence",
        "definition": (
            "The reader's contributions do not survive the session: messages are accepted and "
            "then absent on reload, or the model returns nothing at all."
        ),
        "observed_instance": (
            "Janitor AI — clean email + 6-digit-code signup, but the free model returned 0 "
            "replies across 4 sessions and sent messages did not persist after reload."
        ),
        "detectable_from_transcript": True,
    },
    {
        "code": "F3",
        "name": "Gating censoring",
        "definition": (
            "Progression halts before the probe can be administered, because of a signup wall, "
            "a paid-trial wall, or an unreachable submission control."
        ),
        "observed_instance": (
            "Talefy (7 s teaser, then reader signup + $9.99/7-day trial wall); Joyland (every "
            "chat click opens a login modal); NovelAI (text signup submit unreachable in 6 attempts)."
        ),
        "detectable_from_transcript": True,
    },
    {
        "code": "F4",
        "name": "Transient service degradation",
        "definition": (
            "Progression stalls mid-session for infrastructure reasons, then resumes. "
            "Recoverable, and therefore not a capability failure."
        ),
        "observed_instance": (
            "AI Dungeon — free-queue stall at turn 7; session resumed and passed the turn-15 "
            "probe verbatim. Recorded as turns-before-wall = 7 without being scored as a wall."
        ),
        "detectable_from_transcript": True,
    },
    {
        "code": "F5",
        "name": "Platform delisting",
        "definition": (
            "The product disappears from its distribution channel, orphaning the reader's "
            "continuity and any authored user content."
        ),
        "observed_instance": (
            "Chai AI removed from the iOS App Store in October 2026; SpicyChat removed in late "
            "2026 (companion availability dataset, 10.5281/zenodo.24514920)."
        ),
        "detectable_from_transcript": False,
    },
]

_VERDICTS: dict[str, dict[str, Any]] = {
    "PASS": {
        "mode": "none",
        "mode_code": "F0",
        "label": "pass",
        "drift_detected": False,
        "passed": True,
        "summary": "Planted fact was recalled at or after the probe turn with no contradiction.",
    },
    "F4_TRANSIENT_DEGRADATION": {
        "mode": "F4",
        "mode_code": "F4",
        "label": "transient_degradation",
        "drift_detected": True,
        "passed": True,
        "summary": "Progression stalled after planting but recovered and recalled the fact.",
    },
    "F1_CONTRADICTION": {
        "mode": "F1",
        "mode_code": "F1",
        "label": "silent_state_loss_contradiction",
        "drift_detected": True,
        "passed": False,
        "summary": "A later turn asserts a different value for the planted fact (contradiction).",
    },
    "F1_OMISSION": {
        "mode": "F1",
        "mode_code": "F1",
        "label": "silent_state_loss_omission",
        "drift_detected": True,
        "passed": False,
        "summary": "The probe turn was reached but the planted fact was never recalled (omission).",
    },
    "F2_SESSION_NON_PERSISTENCE": {
        "mode": "F2",
        "mode_code": "F2",
        "label": "session_non_persistence",
        "drift_detected": True,
        "passed": False,
        "summary": "Assistant turns after planting were empty (session did not persist).",
    },
    "F3_GATING_CENSORING": {
        "mode": "F3",
        "mode_code": "F3",
        "label": "right_censored",
        "drift_detected": False,
        "passed": None,
        "summary": "The transcript stops before the probe turn; status is unknown rather than failed.",
    },
    "F5_PLATFORM_DELISTING": {
        "mode": "F5",
        "mode_code": "F5",
        "label": "untestable",
        "drift_detected": False,
        "passed": None,
        "summary": "Platform delisting prevented the session from being administered at all.",
    },
    "FACT_NOT_PLANTED": {
        "mode": "unknown",
        "mode_code": None,
        "label": "not_planted",
        "drift_detected": False,
        "passed": None,
        "summary": "The expected value never appears in the transcript, so no fact was planted.",
    },
    "EMPTY_TRANSCRIPT": {
        "mode": "unknown",
        "mode_code": None,
        "label": "empty_transcript",
        "drift_detected": False,
        "passed": None,
        "summary": "The transcript contains no turns.",
    },
}


def _norm(text: str) -> str:
    return " ".join(str(text).split()).strip().lower()


def _contains(text: str, needle: str) -> bool:
    needle_n = _norm(needle)
    return bool(needle_n) and needle_n in _norm(text)


def normalize_transcript(transcript: Any) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    if not isinstance(transcript, list):
        raise ValueError("transcript must be an array of turns")
    for i, entry in enumerate(transcript):
        if isinstance(entry, str):
            turns.append({"turn": i + 1, "speaker": "unknown", "text": entry})
        elif isinstance(entry, dict):
            text = entry.get("text", entry.get("content", ""))
            raw_turn = entry.get("turn", i + 1)
            try:
                number = int(raw_turn)
            except (TypeError, ValueError):
                number = i + 1
            turns.append(
                {
                    "turn": number,
                    "speaker": str(entry.get("speaker", "unknown")),
                    "text": str(text if text is not None else ""),
                }
            )
        else:
            raise ValueError(f"transcript[{i}] must be a string or an object with a 'text' field")
    return turns


def detect_state_drift(
    fact: Any,
    transcript: Any,
    probe_turn: int | None = None,
    min_gap: int = 2,
    delisted: bool = False,
) -> dict[str, Any]:
    """Check a transcript against a planted fact and classify drift mode."""
    if not isinstance(fact, dict):
        raise ValueError("fact must be an object like {key, expected_value, planted_turn}")
    expected = fact.get("expected_value")
    if expected is None or not str(expected).strip():
        raise ValueError("fact.expected_value is required")
    expected = str(expected).strip()
    key = str(fact.get("key", "")).strip()
    wrong_values = [str(v) for v in (fact.get("wrong_values") or []) if str(v).strip()]
    aliases = [str(a) for a in (fact.get("aliases") or []) if str(a).strip()]
    contradiction_mode = str(fact.get("contradiction_mode", "wrong_values")).lower()

    turns = normalize_transcript(transcript)
    if not turns:
        return _drift_result("EMPTY_TRANSCRIPT", fact, turns, None, None, [], [], [])

    max_turn = max(t["turn"] for t in turns)
    planted_turn = fact.get("planted_turn")
    if planted_turn is not None:
        try:
            planted_turn = int(planted_turn)
        except (TypeError, ValueError):
            raise ValueError("fact.planted_turn must be an integer")
    else:
        for entry in turns:
            if _contains(entry["text"], expected) or any(_contains(entry["text"], a) for a in aliases):
                planted_turn = entry["turn"]
                break

    if planted_turn is None:
        return _drift_result("FACT_NOT_PLANTED", fact, turns, None, None, [], [], [])

    # Even when the caller supplies planted_turn, the fact must actually appear in
    # the transcript — otherwise the premise is false and no verdict is meaningful.
    planted_present = any(
        _contains(entry["text"], expected) or any(_contains(entry["text"], alias) for alias in aliases)
        for entry in turns
    )
    if not planted_present:
        return _drift_result("FACT_NOT_PLANTED", fact, turns, None, None, [], [], [])

    probe_explicit = probe_turn is not None
    probe = probe_turn if probe_turn is not None else max_turn
    try:
        probe = int(probe)
    except (TypeError, ValueError):
        raise ValueError("probe_turn must be an integer")

    post_plant = [t for t in turns if t["turn"] > planted_turn]

    recall_turns = [
        t["turn"] for t in post_plant if _contains(t["text"], expected) or any(_contains(t["text"], a) for a in aliases)
    ]
    contradiction_turns: list[int] = []
    for entry in post_plant:
        contradicted = any(_contains(entry["text"], wrong) for wrong in wrong_values)
        if not contradicted and contradiction_mode == "key_mention_without_value" and key:
            contradicted = _contains(entry["text"], key) and not _contains(entry["text"], expected)
        if contradicted:
            contradiction_turns.append(entry["turn"])

    empty_turns = [t["turn"] for t in post_plant if not str(t["text"]).strip()]
    recall_at_probe = [t for t in recall_turns if t >= probe]
    # A contradiction is positive evidence of drift at any point after planting,
    # not only at the probe turn, so it is not filtered by `probe`.
    contradiction_after_plant = list(contradiction_turns)

    # A stall is positive evidence of a mid-session interruption: an empty turn or a
    # missing turn number between planting and recall, or a repeated assistant reply.
    stall = False
    if recall_at_probe:
        first_recall = min(recall_at_probe)
        present = {t["turn"] for t in post_plant if planted_turn < t["turn"] <= first_recall}
        missing = [n for n in range(planted_turn + 1, first_recall + 1) if n not in present]
        stall = bool([t for t in empty_turns if planted_turn < t <= first_recall]) or bool(missing)
    else:
        stall = bool(empty_turns)

    if not stall:
        previous = None
        for entry in post_plant:
            text = _norm(entry["text"])
            if text and text == previous:
                stall = True
                break
            previous = text or previous

    reached_probe = max_turn >= probe if probe_explicit else max_turn >= planted_turn + max(1, int(min_gap))

    if delisted:
        verdict = "F5_PLATFORM_DELISTING"
    elif contradiction_after_plant:
        verdict = "F1_CONTRADICTION"
    elif recall_at_probe and stall:
        verdict = "F4_TRANSIENT_DEGRADATION"
    elif recall_at_probe:
        verdict = "PASS"
    elif not reached_probe:
        verdict = "F3_GATING_CENSORING"
    elif empty_turns:
        verdict = "F2_SESSION_NON_PERSISTENCE"
    else:
        verdict = "F1_OMISSION"

    return _drift_result(
        verdict,
        fact,
        turns,
        planted_turn,
        probe,
        recall_turns,
        contradiction_turns,
        empty_turns,
        extra={
            "stall_detected": stall,
            "probe_reached": reached_probe,
            "last_turn": max_turn,
        },
    )


def _drift_result(
    verdict: str,
    fact: dict[str, Any],
    turns: list[dict[str, Any]],
    planted_turn: int | None,
    probe: int | None,
    recall_turns: list[int],
    contradiction_turns: list[int],
    empty_turns: list[int],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = _VERDICTS[verdict]
    per_turn = []
    for entry in turns:
        if planted_turn is not None and entry["turn"] <= planted_turn:
            relation = "at_or_before_planting"
        elif not str(entry["text"]).strip():
            relation = "empty"
        elif entry["turn"] in recall_turns:
            relation = "recalled"
        elif entry["turn"] in contradiction_turns:
            relation = "contradicted"
        else:
            relation = "omitted"
        per_turn.append(
            {
                "turn": entry["turn"],
                "speaker": entry["speaker"],
                "relation": relation,
                "text": entry["text"],
            }
        )

    result: dict[str, Any] = {
        "ok": True,
        "verdict": verdict,
        "label": spec["label"],
        "mode": spec["mode"],
        "mode_code": spec["mode_code"],
        "drift_detected": spec["drift_detected"],
        "passed": spec["passed"],
        "summary": spec["summary"],
        "fact": {
            "key": fact.get("key"),
            "expected_value": fact.get("expected_value"),
            "planted_turn": planted_turn,
        },
        "probe_turn": probe,
        "evidence": {
            "turns_analyzed": len(turns),
            "planted_turn": planted_turn,
            "probe_turn": probe,
            "recall_turns": recall_turns,
            "contradiction_turns": contradiction_turns,
            "empty_turns": empty_turns,
        },
        "per_turn": per_turn,
        "taxonomy": DRIFT_TAXONOMY,
        "taxonomy_source": {
            "title": (
                "State Drift in Consumer LLM Interactive Fiction: A 15-Turn Empirical Benchmark "
                "Across 10 Platforms and a 207-Line Deterministic Story-State Kernel"
            ),
            "author": "Ouba Studio",
            "year": 2026,
            "doi": "10.5281/zenodo.24549412",
            "url": "https://doi.org/10.5281/zenodo.24549412",
        },
        "deterministic": True,
    }
    if extra:
        result["evidence"].update(extra)
    return result
