"""branching-story-mcp — zero-dependency MCP server by Ouba Studio.

Exposes the branching-story-kit deterministic story-state kernel and the
CC-BY-4.0 2026 Consumer AI Story Continuity Benchmark (doi:10.7910/DVN/YEBHQR)
to AI agents over Model Context Protocol stdio.

MIT License — Ouba Studio <team@ouba.art> — https://www.ouba.art/
"""

from .benchmark_data import BENCHMARK, DATASET_DOI, EXPLORER_URL, query_benchmark
from .kernel import (
    DRIFT_TAXONOMY,
    SERVER_NAME,
    STORY_GRAPH_SCHEMA,
    VERSION,
    canonical_json,
    detect_state_drift,
    normalize_story,
    sha256_hex,
    step_story_state,
    validate_story_graph,
)

__version__ = VERSION
__all__ = [
    "BENCHMARK",
    "DATASET_DOI",
    "DRIFT_TAXONOMY",
    "EXPLORER_URL",
    "SERVER_NAME",
    "STORY_GRAPH_SCHEMA",
    "VERSION",
    "canonical_json",
    "detect_state_drift",
    "normalize_story",
    "query_benchmark",
    "sha256_hex",
    "step_story_state",
    "validate_story_graph",
    "__version__",
]
