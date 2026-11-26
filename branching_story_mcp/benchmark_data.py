"""Verified 2026 Consumer AI Story Continuity Benchmark data (CC-BY-4.0).

Evaluation date: 2026-11-15. Primary dataset: Harvard Dataverse
doi:10.7910/DVN/YEBHQR. Every number below is transcribed from the published
per-product matrix (``benchmark_results_2026_11_15.csv``).

Protocol: $0 spent, email-only identity, no CAPTCHA solving, no OAuth linkage,
no payment card. A trivial fact ("My cat's name is Marmalade.") was planted at
turn 2 and probed at turn 15.

Status vocabulary
-----------------
``pass``           recalled at the turn-15 probe
``fail``           probe administered, fact not recalled (silent state loss)
``right_censored`` progression halted before the probe could be administered
``untestable``     no free/available session existed under the protocol
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "BENCHMARK",
    "DATASET_DOI",
    "EXPLORER_URL",
    "STATUS_ALIASES",
    "PLATFORM_ALIASES",
    "query_benchmark",
    "benchmark_citation",
]

DATASET_DOI = "10.7910/DVN/YEBHQR"
EXPLORER_URL = "https://www.ouba.art/tools/benchmark-explorer"
TAXONOMY_DOI = "10.5281/zenodo.24549412"

BENCHMARK: dict[str, Any] = {
    "id": "ai-story-apps-benchmark-2026",
    "title": "2026 Consumer AI Story Continuity Benchmark",
    "subtitle": "10-Platform, 15-Turn Verbatim Recall Matrix",
    "evaluation_date": "2026-11-15",
    "published": "2026-11-26",
    "publisher": "Ouba Studio",
    "license": "CC-BY-4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "dataset_doi": DATASET_DOI,
    "dataset_url": f"https://doi.org/{DATASET_DOI}",
    "explorer_url": EXPLORER_URL,
    "taxonomy_doi": TAXONOMY_DOI,
    "planted_fact": "My cat's name is Marmalade.",
    "planted_turn": 2,
    "probe_turn": 15,
    "protocol": {
        "spend_usd": 0,
        "identity": "email-only",
        "captcha_solving": False,
        "oauth_linkage": False,
        "payment_card": False,
        "content_rating": "PG-13",
    },
    "summary": {
        "products_evaluated": 10,
        "probe_administered": 4,
        "recalled_unconditional": 3,
        "recalled_unconditional_rate": 0.30,
        "recalled_conditional": 3,
        "recalled_conditional_rate": 0.75,
        "right_censored": 4,
        "untestable": 2,
        "ttfs_median_s": 19,
        "ttfs_range_s": [7, 70],
        "mean_reply_latency_s": 5.3,
        "ad_interruptions_observed": 0,
        "no_signup_gate_before_reading": 3,
    },
    "platforms": [
        {
            "platform": "Ouba",
            "slug": "ouba",
            "category": "Reader-first AI fiction",
            "status": "pass",
            "turns_completed": 20,
            "turns_before_wall": 20,
            "turn15_probe": "Pass (verbatim)",
            "ttfs_s": 15,
            "reply_latency_s": 7,
            "ads_observed": "None (0 frames)",
            "signup_gate": False,
            "failure_mode": None,
            "notes": "20 turns, verbatim recall of the planted fact at turn 15.",
        },
        {
            "platform": "Talkie",
            "slug": "talkie",
            "category": "Companion chatbot",
            "status": "pass",
            "turns_completed": 20,
            "turns_before_wall": 20,
            "turn15_probe": "Pass",
            "ttfs_s": 17,
            "reply_latency_s": 3,
            "ads_observed": "None seen",
            "signup_gate": False,
            "failure_mode": None,
            "notes": "20 turns, planted fact recalled at turn 15.",
        },
        {
            "platform": "Character.AI",
            "slug": "character-ai",
            "category": "Companion chatbot",
            "status": "fail",
            "turns_completed": 20,
            "turns_before_wall": 20,
            "turn15_probe": "Fail",
            "ttfs_s": 21,
            "reply_latency_s": 3,
            "ads_observed": "1 tracking pixel",
            "signup_gate": True,
            "failure_mode": "F1",
            "notes": (
                "20 turns at ~3 s/reply, on-persona throughout, but the turn-15 query returned a "
                "cafe menu and never produced 'Marmalade'. Silent state loss."
            ),
        },
        {
            "platform": "AI Dungeon",
            "slug": "ai-dungeon",
            "category": "Open sandbox",
            "status": "pass",
            "turns_completed": 7,
            "turns_before_wall": 7,
            "turn15_probe": "Pass (verbatim)",
            "ttfs_s": 70,
            "reply_latency_s": 8,
            "ads_observed": "None seen",
            "signup_gate": False,
            "failure_mode": "F4",
            "notes": (
                "Transient free-queue stall at turn 7; session resumed and passed the turn-15 probe "
                "verbatim. Recorded as turns-before-wall = 7 without being scored as a wall."
            ),
        },
        {
            "platform": "Janitor AI",
            "slug": "janitor-ai",
            "category": "Companion chatbot",
            "status": "right_censored",
            "turns_completed": 0,
            "turns_before_wall": 0,
            "turn15_probe": "Not reached",
            "ttfs_s": 45,
            "reply_latency_s": None,
            "ads_observed": "None seen",
            "signup_gate": True,
            "failure_mode": "F2",
            "notes": (
                "Clean email + 6-digit-code signup, but the free model returned 0 replies across 4 "
                "sessions and sent messages did not persist after reload."
            ),
        },
        {
            "platform": "Talefy",
            "slug": "talefy",
            "category": "Reader-first AI fiction",
            "status": "right_censored",
            "turns_completed": 0,
            "turns_before_wall": 0,
            "turn15_probe": "Not reached",
            "ttfs_s": 7,
            "reply_latency_s": None,
            "ads_observed": "None seen",
            "signup_gate": True,
            "failure_mode": "F3",
            "notes": "7 s teaser, then reader signup + $9.99/7-day trial wall.",
        },
        {
            "platform": "Joyland",
            "slug": "joyland",
            "category": "Companion chatbot",
            "status": "right_censored",
            "turns_completed": 0,
            "turns_before_wall": 0,
            "turn15_probe": "Not reached",
            "ttfs_s": None,
            "reply_latency_s": None,
            "ads_observed": "None seen",
            "signup_gate": True,
            "failure_mode": "F3",
            "notes": "Every chat click opens a login modal; email-only control unaddressable in 6 attempts.",
        },
        {
            "platform": "NovelAI",
            "slug": "novelai",
            "category": "AI writing tool",
            "status": "right_censored",
            "turns_completed": 0,
            "turns_before_wall": 0,
            "turn15_probe": "Not reached",
            "ttfs_s": None,
            "reply_latency_s": None,
            "ads_observed": "None seen",
            "signup_gate": True,
            "failure_mode": "F3",
            "notes": "Text signup submit unreachable in 6 attempts.",
        },
        {
            "platform": "Chai",
            "slug": "chai",
            "category": "Companion chatbot",
            "status": "untestable",
            "turns_completed": None,
            "turns_before_wall": None,
            "turn15_probe": "Not tested",
            "ttfs_s": None,
            "reply_latency_s": None,
            "ads_observed": "Not tested",
            "signup_gate": None,
            "failure_mode": "F5",
            "notes": (
                "Untestable: no free web version on 2026-11-15 (parked domain, non-resolving chat "
                "subdomain, mobile-only). Chai AI was removed from the iOS App Store in October 2026."
            ),
        },
        {
            "platform": "Galatea",
            "slug": "galatea",
            "category": "Pre-written serial",
            "status": "untestable",
            "turns_completed": None,
            "turns_before_wall": None,
            "turn15_probe": "Not tested",
            "ttfs_s": None,
            "reply_latency_s": None,
            "ads_observed": "Not tested",
            "signup_gate": True,
            "failure_mode": "F3",
            "notes": "Untestable: paid serialized subscription with no free AI tier.",
        },
    ],
}

STATUS_ALIASES: dict[str, str] = {
    "pass": "pass",
    "passed": "pass",
    "passes": "pass",
    "ok": "pass",
    "verbatim": "pass",
    "fail": "fail",
    "failed": "fail",
    "failure": "fail",
    "silent_state_loss": "fail",
    "right_censored": "right_censored",
    "right-censored": "right_censored",
    "censored": "right_censored",
    "not_reached": "right_censored",
    "untestable": "untestable",
    "not_tested": "untestable",
    "n/a": "untestable",
}

PLATFORM_ALIASES: dict[str, str] = {
    "ouba": "Ouba",
    "ouba.art": "Ouba",
    "talkie": "Talkie",
    "character.ai": "Character.AI",
    "characterai": "Character.AI",
    "character ai": "Character.AI",
    "cai": "Character.AI",
    "ai dungeon": "AI Dungeon",
    "aidungeon": "AI Dungeon",
    "aid": "AI Dungeon",
    "janitor": "Janitor AI",
    "janitor ai": "Janitor AI",
    "janitorai": "Janitor AI",
    "talefy": "Talefy",
    "joyland": "Joyland",
    "novelai": "NovelAI",
    "novel ai": "NovelAI",
    "chai": "Chai",
    "chai ai": "Chai",
    "galatea": "Galatea",
}

_STATUS_FILTERS: dict[str, set[str]] = {
    "pass": {"pass"},
    "fail": {"fail"},
    "right_censored": {"right_censored"},
    "untestable": {"untestable"},
    "tested": {"pass", "fail"},
    "recall": {"pass", "fail"},
}


def _platforms() -> list[dict[str, Any]]:
    return [dict(p) for p in BENCHMARK["platforms"]]


def query_benchmark(platform: str | None = None, status: str | None = None) -> dict[str, Any]:
    """Filter the benchmark matrix and return structured JSON plus citation."""
    platforms = _platforms()
    filters: dict[str, Any] = {}
    warnings: list[str] = []
    suggestions: list[str] = []

    if platform not in (None, ""):
        needle = str(platform).strip()
        canonical = PLATFORM_ALIASES.get(needle.lower())
        if canonical:
            matches = [p for p in platforms if p["platform"] == canonical]
        else:
            matches = [p for p in platforms if needle.lower() in p["platform"].lower()]
            if not matches:
                matches = [p for p in platforms if needle.lower() in p["slug"]]
        if not matches:
            suggestions = [p["platform"] for p in platforms]
            warnings.append(
                f"unknown platform {platform!r}; known platforms: " + ", ".join(suggestions)
            )
        platforms = matches
        filters["platform"] = platform

    if status not in (None, ""):
        needle = str(status).strip().lower().replace("-", "_").replace(" ", "_")
        canonical_status = STATUS_ALIASES.get(needle)
        if canonical_status is None and needle in _STATUS_FILTERS:
            allowed = _STATUS_FILTERS[needle]
        elif canonical_status is not None:
            allowed = {canonical_status}
        else:
            allowed = set()
            warnings.append(
                f"unknown status {status!r}; expected one of pass, fail, right_censored, untestable"
            )
        platforms = [p for p in platforms if p["status"] in allowed]
        filters["status"] = status

    return {
        "benchmark": {
            "id": BENCHMARK["id"],
            "title": BENCHMARK["title"],
            "subtitle": BENCHMARK["subtitle"],
            "evaluation_date": BENCHMARK["evaluation_date"],
            "publisher": BENCHMARK["publisher"],
            "license": BENCHMARK["license"],
            "license_url": BENCHMARK["license_url"],
            "dataset_doi": BENCHMARK["dataset_doi"],
            "dataset_url": BENCHMARK["dataset_url"],
            "explorer_url": BENCHMARK["explorer_url"],
            "taxonomy_doi": BENCHMARK["taxonomy_doi"],
            "planted_fact": BENCHMARK["planted_fact"],
            "planted_turn": BENCHMARK["planted_turn"],
            "probe_turn": BENCHMARK["probe_turn"],
            "protocol": dict(BENCHMARK["protocol"]),
            "summary": dict(BENCHMARK["summary"]),
        },
        "filters": filters,
        "count": len(platforms),
        "results": platforms,
        "warnings": warnings,
        "citation": benchmark_citation(),
    }


def benchmark_citation() -> dict[str, Any]:
    """Full APA + BibTeX citation for the benchmark dataset."""
    return {
        "apa": (
            "Ouba Studio. (2026). Interactive Fiction & AI Story Apps Benchmark Dataset (2026) "
            "[Data set]. Harvard Dataverse. https://doi.org/10.7910/DVN/YEBHQR"
        ),
        "bibtex": (
            "@dataset{ouba_studio_2026_ai_story_benchmark,\n"
            "  author    = {{Ouba Studio}},\n"
            "  title     = {Interactive Fiction \\& AI Story Apps Benchmark Dataset (2026)},\n"
            "  year      = {2026},\n"
            "  publisher = {Harvard Dataverse},\n"
            "  doi       = {10.7910/DVN/YEBHQR},\n"
            "  url       = {https://doi.org/10.7910/DVN/YEBHQR},\n"
            "  license   = {CC-BY-4.0},\n"
            "  note      = {10-platform consumer AI story continuity benchmark; evaluation date 2026-11-15}\n"
            "}"
        ),
        "doi": DATASET_DOI,
        "doi_url": f"https://doi.org/{DATASET_DOI}",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "explorer_url": EXPLORER_URL,
        "taxonomy_doi": TAXONOMY_DOI,
        "taxonomy_url": f"https://doi.org/{TAXONOMY_DOI}",
    }
