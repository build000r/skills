"""
Portfolio-level opportunity mining for the skills catalog.

This complements per-skill review by scanning transcript history across the
catalog and surfacing:
- repeated manual workflows that should become skills
- requests that look like an existing skill but do not activate it
- overlapping skills that should likely be consolidated
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from lib.skill_review import (
    collect_session_data,
    command_stem,
    find_skill_path_hits,
    has_user_trigger,
    is_assistant_ack,
    list_session_files,
    normalize_tool_name,
    parse_timestamp,
    truncate,
)

RAW_SHELL_STEMS = {"rg", "sed", "find", "git", "ls", "ssh", "docker", "curl"}
SHORT_TOKENS = {"ai", "qa", "db", "do", "ci", "cd", "ui", "ux", "ip", "vm", "qr", "ocr", "pdf", "ssh", "api"}
STOPWORDS = {
    "a",
    "about",
    "across",
    "after",
    "again",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "before",
    "build",
    "by",
    "can",
    "check",
    "create",
    "debug",
    "design",
    "do",
    "for",
    "from",
    "get",
    "help",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "let",
    "look",
    "make",
    "me",
    "mode",
    "my",
    "need",
    "new",
    "of",
    "on",
    "or",
    "our",
    "out",
    "please",
    "project",
    "repo",
    "review",
    "run",
    "session",
    "should",
    "skill",
    "skills",
    "so",
    "some",
    "that",
    "the",
    "their",
    "them",
    "this",
    "to",
    "use",
    "using",
    "want",
    "we",
    "what",
    "when",
    "with",
    "work",
    "workflow",
    "you",
    "your",
}
DISCOVERABILITY_MIN_SCORE = 3.0
MIN_CARD_SCORE = 14


def _tokenize(text: str) -> list[str]:
    """Return compact lowercase tokens for similarity matching."""
    tokens = []
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if token in STOPWORDS:
            continue
        if len(token) >= 3 or token in SHORT_TOKENS:
            tokens.append(token)
    return tokens


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract a simple YAML frontmatter block and return the remaining body."""
    stripped = text.lstrip()
    if not stripped.startswith("---\n"):
        return {}, text

    parts = stripped.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text

    block, body = parts
    data: dict[str, str] = {}
    for line in block.splitlines()[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            data[key] = value
    return data, body


def _quoted_phrases(text: str) -> list[str]:
    """Collect quoted trigger phrases from a description block."""
    return [match.strip() for match in re.findall(r'"([^"]+)"', text) if match.strip()]


def _first_heading(body: str) -> str | None:
    """Return the first markdown heading in the body."""
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _body_excerpt(body: str, max_lines: int = 60) -> str:
    """Return a concise body excerpt for content similarity and evidence."""
    kept = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        kept.append(stripped)
        if len(kept) >= max_lines:
            break
    return "\n".join(kept)


def load_skill_catalog(skills_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Load top-level skills from a repo or installed skills directory."""
    root = Path(skills_root) if skills_root else Path(__file__).resolve().parents[3]
    skills = []

    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        skill_path = path / "SKILL.md"
        if not skill_path.exists():
            continue

        text = skill_path.read_text(encoding="utf-8")
        frontmatter, body = _frontmatter(text)
        name = frontmatter.get("name") or path.name
        description = frontmatter.get("description", "")
        heading = _first_heading(body) or name
        trigger_phrases = _quoted_phrases(description)
        discovery_text = " ".join(
            [
                name.replace("-", " "),
                path.name.replace("-", " "),
                description,
                heading,
                " ".join(trigger_phrases),
            ]
        )
        excerpt = _body_excerpt(body)
        skills.append(
            {
                "name": name,
                "slug": path.name,
                "path": str(skill_path),
                "description": description,
                "heading": heading,
                "excerpt": excerpt,
                "trigger_phrases": trigger_phrases,
                "name_tokens": set(_tokenize(name.replace("-", " "))),
                "discovery_tokens": set(_tokenize(discovery_text)),
                "content_tokens": set(_tokenize(excerpt)),
                "has_modes": ("modes/" in body.lower()) or ("mode selection" in body.lower()),
            }
        )

    return skills


def _skill_aliases(skill: dict[str, Any]) -> list[str]:
    """Return the stable aliases used for trigger/path detection."""
    aliases = [skill["name"]]
    if skill["slug"] != skill["name"]:
        aliases.append(skill["slug"])
    return aliases


def _path_hit_for_skill(arguments: Any, skill: dict[str, Any]) -> str | None:
    """Return one representative skill-path hit when present."""
    for alias in _skill_aliases(skill):
        hits = find_skill_path_hits(arguments, alias)
        if hits:
            return hits[0]
    return None


def _user_trigger_for_skill(user_messages: list[str], skill: dict[str, Any]) -> bool:
    """Detect an explicit user request for a skill."""
    for alias in _skill_aliases(skill):
        if any(has_user_trigger(message, alias) for message in user_messages):
            return True
    return False


def _assistant_ack_for_skill(assistant_messages: list[str], skill: dict[str, Any]) -> bool:
    """Detect the standard acknowledgement marker for a skill."""
    for alias in _skill_aliases(skill):
        if any(is_assistant_ack(message, alias) for message in assistant_messages):
            return True
    return False


def _request_similarity(session: dict[str, Any], skill: dict[str, Any]) -> dict[str, Any]:
    """Score how strongly a user request resembles a skill's surface area."""
    user_request = session.get("user_request") or ""
    request_tokens = session.get("request_tokens", set())
    if not user_request or not request_tokens:
        return {
            "skill": skill["name"],
            "score": 0.0,
            "normalized": 0.0,
            "signal_tokens": [],
            "trigger_hits": [],
        }

    text = user_request.lower()
    overlap = request_tokens & skill["discovery_tokens"]
    name_overlap = request_tokens & skill["name_tokens"]
    trigger_hits = [phrase for phrase in skill["trigger_phrases"] if phrase.lower() in text]
    score = float(len(overlap)) + (1.5 * len(name_overlap)) + (2.0 * len(trigger_hits))
    normalized = round(score / max(4, len(request_tokens)), 3)

    return {
        "skill": skill["name"],
        "score": round(score, 3),
        "normalized": normalized,
        "signal_tokens": sorted(overlap)[:6],
        "trigger_hits": trigger_hits[:3],
    }


def _session_summary(provider: str, path: Path, mtime: datetime, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect one transcript summary against the current skill catalog."""
    session = collect_session_data(provider, path, mtime)
    command_stems: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    raw_shell_stems: set[str] = set()

    for call in session["function_calls"]:
        tool_name = normalize_tool_name(call.get("name"))
        if tool_name:
            tool_counts[tool_name] += 1

        command = call.get("command")
        if command:
            stem = command_stem(command)
            if stem:
                command_stems[stem] += 1
                if stem in RAW_SHELL_STEMS:
                    raw_shell_stems.add(stem)

    direct_matches = []
    for skill in catalog:
        matched_on = set()
        path_hit = None
        if _user_trigger_for_skill(session["user_messages"], skill):
            matched_on.add("user_trigger")
        if _assistant_ack_for_skill(session["assistant_messages"], skill):
            matched_on.add("assistant_ack")
        for call in session["function_calls"]:
            path_hit = _path_hit_for_skill(call.get("arguments"), skill)
            if path_hit:
                matched_on.add("skill_path")
                break
        if not matched_on:
            continue

        direct_matches.append(
            {
                "skill": skill["name"],
                "match_score": (
                    (4 if "assistant_ack" in matched_on else 0)
                    + (3 if "skill_path" in matched_on else 0)
                    + (2 if "user_trigger" in matched_on else 0)
                ),
                "matched_on": sorted(matched_on),
                "path_hit": path_hit,
            }
        )

    direct_matches.sort(
        key=lambda item: (
            item["match_score"],
            1 if "assistant_ack" in item["matched_on"] else 0,
            1 if "skill_path" in item["matched_on"] else 0,
        ),
        reverse=True,
    )

    user_request = session["user_messages"][0] if session["user_messages"] else None
    request_tokens = set(_tokenize(user_request or ""))
    suggestion_scores = []
    for skill in catalog:
        suggestion = _request_similarity(
            {
                "user_request": user_request,
                "request_tokens": request_tokens,
            },
            skill,
        )
        if suggestion["score"] > 0:
            suggestion_scores.append(suggestion)
    suggestion_scores.sort(key=lambda item: (item["score"], item["normalized"]), reverse=True)

    activated_skills = [
        match["skill"]
        for match in direct_matches
        if "assistant_ack" in match["matched_on"] or "skill_path" in match["matched_on"]
    ]
    requested_skills = [match["skill"] for match in direct_matches if "user_trigger" in match["matched_on"]]

    return {
        "provider": provider,
        "file": str(path),
        "project": session["project"],
        "timestamp": session["timestamp"].isoformat(),
        "user_request": truncate(user_request, 500) if user_request else None,
        "request_tokens": sorted(request_tokens),
        "tool_counts": dict(tool_counts),
        "command_stems": dict(command_stems),
        "raw_shell_stems": sorted(raw_shell_stems),
        "direct_matches": direct_matches[:5],
        "activated_skills": activated_skills,
        "requested_skills": requested_skills,
        "top_suggested_skills": suggestion_scores[:5],
        "task_complete": session["task_complete"],
    }


def scan_skill_portfolio(
    source: str = "both",
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
    skills_root: str | Path | None = None,
) -> dict[str, Any]:
    """Scan transcripts and summarize portfolio-level demand across skills."""
    since = since or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    until = until or datetime.now(timezone.utc)
    catalog = load_skill_catalog(skills_root)
    sessions = []
    sessions_scanned = 0
    providers = Counter()

    for provider, path, mtime in list_session_files(source, since, until):
        sessions_scanned += 1
        session = _session_summary(provider, path, mtime, catalog)
        if not session["user_request"] and not session["command_stems"]:
            continue
        sessions.append(session)
        providers[provider] += 1
        if len(sessions) >= limit:
            break

    activated_counts = Counter()
    suggested_counts = Counter()
    for session in sessions:
        activated_counts.update(session["activated_skills"])
        for suggestion in session["top_suggested_skills"][:3]:
            if suggestion["score"] >= DISCOVERABILITY_MIN_SCORE:
                suggested_counts.update([suggestion["skill"]])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "skills_root": str(Path(skills_root) if skills_root else Path(__file__).resolve().parents[3]),
        "catalog": catalog,
        "sessions_scanned": sessions_scanned,
        "sessions_analyzed": len(sessions),
        "providers": dict(providers),
        "sessions": sessions,
        "catalog_summary": {
            "skills_loaded": len(catalog),
            "activated_counts": dict(activated_counts),
            "suggested_counts": dict(suggested_counts),
        },
    }


def _coverage_weight(total_runs: int, overall_runs: int) -> float:
    """Favor issues that affect non-trivial portions of the scanned sessions."""
    if overall_runs <= 0:
        return 1.0
    fraction = total_runs / overall_runs
    return 0.7 + 0.3 * min(fraction / 0.35, 1.0)


def _recency_weight(timestamps: list[str], now: datetime) -> float:
    """Favor opportunities backed by recent sessions."""
    if not timestamps:
        return 1.0
    latest = max(parse_timestamp(value, now) for value in timestamps)
    age_days = max(0, (now - latest).days)
    if age_days <= 7:
        return 1.25
    if age_days <= 30:
        return 1.1
    return 1.0


def _jaccard(left: set[str], right: set[str]) -> float:
    """Return a stable Jaccard similarity."""
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _cluster_sessions(sessions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Cluster low-coverage sessions into repeated workflow components."""
    if not sessions:
        return []

    adjacency = {idx: set() for idx in range(len(sessions))}
    token_sets = [set(session["request_tokens"]) for session in sessions]
    stem_sets = [set(session["raw_shell_stems"]) for session in sessions]

    for left, right in combinations(range(len(sessions)), 2):
        token_overlap = len(token_sets[left] & token_sets[right])
        stem_overlap = len(stem_sets[left] & stem_sets[right])
        if token_overlap >= 2 or (token_overlap >= 1 and stem_overlap >= 1):
            adjacency[left].add(right)
            adjacency[right].add(left)

    clusters = []
    seen = set()
    for idx in range(len(sessions)):
        if idx in seen:
            continue
        queue = [idx]
        component = []
        seen.add(idx)
        while queue:
            current = queue.pop()
            component.append(sessions[current])
            for neighbor in adjacency[current]:
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append(neighbor)
        clusters.append(component)

    return clusters


def _suggest_skill_name(cluster: list[dict[str, Any]]) -> str:
    """Generate a draft skill name from repeated request tokens."""
    token_counts: Counter[str] = Counter()
    for session in cluster:
        token_counts.update(session["request_tokens"])
    tokens = [token for token, _ in token_counts.most_common(4) if token not in {"debug", "check", "review"}]
    if not tokens:
        return "new-workflow-skill"
    return "-".join(tokens[:3])


def _discoverability_cards(
    sessions: list[dict[str, Any]],
    overall_runs: int,
    max_evidence: int,
    now: datetime,
) -> list[dict[str, Any]]:
    """Generate cards for requests that resemble existing skills but do not activate them."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for session in sessions:
        if session["activated_skills"]:
            continue
        suggestions = session.get("top_suggested_skills", [])
        if not suggestions:
            continue
        best = suggestions[0]
        if best["score"] < DISCOVERABILITY_MIN_SCORE:
            continue
        grouped[best["skill"]].append(session)

    cards = []
    total_sessions = max(1, overall_runs)
    for skill_name, skill_sessions in sorted(grouped.items()):
        timestamps = [session["timestamp"] for session in skill_sessions]
        coverage_weight = _coverage_weight(len(skill_sessions), total_sessions)
        confidence = sum(
            session["top_suggested_skills"][0]["normalized"]
            for session in skill_sessions
            if session["top_suggested_skills"]
        ) / max(1, len(skill_sessions))
        score = round(len(skill_sessions) * 10 * coverage_weight * _recency_weight(timestamps, now) * (0.9 + confidence))
        if score < MIN_CARD_SCORE:
            continue

        cards.append(
            {
                "issue_type": "skill-discoverability-gap",
                "score": score,
                "severity": "high" if len(skill_sessions) >= 3 else "medium",
                "scope": skill_name,
                "affected_runs": len(skill_sessions),
                "total_runs": total_sessions,
                "prevalence": round(len(skill_sessions) / total_sessions, 3),
                "hypothesis": (
                    "Users are asking for work that looks like an existing skill, but the skill is not "
                    "being activated consistently from the natural-language request."
                ),
                "recommendation": (
                    f"Tighten trigger phrases, aliases, and README install guidance for `{skill_name}` "
                    "before creating a new skill for the same demand surface."
                ),
                "target_files": [f"{skill_name}/SKILL.md", "README.md"],
                "supporting_metrics": {
                    "average_match_confidence": round(confidence, 3),
                    "top_request_tokens": sorted(
                        Counter(token for session in skill_sessions for token in session["request_tokens"]).keys()
                    )[:6],
                },
                "evidence": [
                    {
                        "timestamp": session["timestamp"],
                        "signal": (
                            f"suggested `{session['top_suggested_skills'][0]['skill']}` "
                            f"via {', '.join(session['top_suggested_skills'][0]['signal_tokens']) or 'catalog overlap'}"
                        ),
                        "user_request": session["user_request"],
                    }
                    for session in skill_sessions[:max_evidence]
                ],
                "followup_brief": (
                    f"Improve discoverability for `{skill_name}` from transcript demand. "
                    f"Affected runs: {len(skill_sessions)}/{total_sessions}."
                ),
            }
        )

    return cards


def _creation_cards(
    sessions: list[dict[str, Any]],
    overall_runs: int,
    min_cluster_runs: int,
    max_evidence: int,
    now: datetime,
) -> list[dict[str, Any]]:
    """Generate cards for repeated workflows with weak catalog overlap."""
    creation_candidates = []
    for session in sessions:
        if session["activated_skills"]:
            continue
        suggestions = session.get("top_suggested_skills", [])
        if suggestions and suggestions[0]["score"] >= DISCOVERABILITY_MIN_SCORE:
            continue
        creation_candidates.append(session)

    cards = []
    total_sessions = max(1, overall_runs)
    for cluster in _cluster_sessions(creation_candidates):
        if len(cluster) < min_cluster_runs:
            continue

        timestamps = [session["timestamp"] for session in cluster]
        raw_stems = Counter(stem for session in cluster for stem in session["raw_shell_stems"])
        token_counts = Counter(token for session in cluster for token in session["request_tokens"])
        suggested_name = _suggest_skill_name(cluster)
        coverage_weight = _coverage_weight(len(cluster), total_sessions)
        automation_bonus = 1.0 + min(len(raw_stems), 3) * 0.08
        score = round(len(cluster) * 10 * coverage_weight * automation_bonus * _recency_weight(timestamps, now))
        if score < MIN_CARD_SCORE:
            continue

        cards.append(
            {
                "issue_type": "skill-creation-opportunity",
                "score": score,
                "severity": "high" if len(cluster) >= 4 else "medium",
                "scope": suggested_name,
                "affected_runs": len(cluster),
                "total_runs": total_sessions,
                "prevalence": round(len(cluster) / total_sessions, 3),
                "hypothesis": (
                    "A repeated manual workflow is showing up in transcripts with weak overlap to the "
                    "current skill catalog, so operators are rebuilding the process ad hoc."
                ),
                "recommendation": (
                    f"Draft a new skill around `{suggested_name}` with triggers taken from the repeated "
                    "user requests and helper scripts for the recurring command path."
                ),
                "target_files": [suggested_name + "/SKILL.md", suggested_name + "/scripts/"],
                "supporting_metrics": {
                    "top_request_tokens": [token for token, _ in token_counts.most_common(6)],
                    "top_raw_shell_stems": [stem for stem, _ in raw_stems.most_common(4)],
                    "projects": sorted(
                        {
                            Path(str(session.get("project") or "unknown")).name or "unknown"
                            for session in cluster
                        }
                    ),
                },
                "evidence": [
                    {
                        "timestamp": session["timestamp"],
                        "signal": (
                            "weak catalog overlap"
                            + (
                                f"; raw shell stems: {', '.join(session['raw_shell_stems'])}"
                                if session["raw_shell_stems"]
                                else ""
                            )
                        ),
                        "user_request": session["user_request"],
                    }
                    for session in cluster[:max_evidence]
                ],
                "followup_brief": (
                    f"Create a new skill for the repeated `{suggested_name}` workflow. "
                    f"Affected runs: {len(cluster)}/{total_sessions}."
                ),
            }
        )

    return cards


def _pair_session_overlap(
    sessions: list[dict[str, Any]],
    threshold: float = DISCOVERABILITY_MIN_SCORE,
) -> tuple[dict[tuple[str, str], int], Counter[str]]:
    """Measure how often skills compete for the same request surface."""
    pair_counts: dict[tuple[str, str], int] = Counter()
    per_skill: Counter[str] = Counter()

    for session in sessions:
        candidates = []
        for suggestion in session.get("top_suggested_skills", []):
            if suggestion["score"] >= threshold:
                candidates.append(suggestion["skill"])
        for skill in session.get("activated_skills", []):
            candidates.append(skill)
        unique_candidates = sorted(set(candidates))
        per_skill.update(unique_candidates)
        for left, right in combinations(unique_candidates, 2):
            pair_counts[(left, right)] += 1

    return pair_counts, per_skill


def _canonical_skill(left: dict[str, Any], right: dict[str, Any]) -> tuple[str, str]:
    """Pick the likely canonical skill name for a consolidation recommendation."""
    if len(left["name"]) < len(right["name"]):
        return left["name"], right["name"]
    if len(right["name"]) < len(left["name"]):
        return right["name"], left["name"]
    return sorted([left["name"], right["name"]])[0], sorted([left["name"], right["name"]])[1]


def _consolidation_cards(
    catalog: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    max_evidence: int,
) -> list[dict[str, Any]]:
    """Generate cards for heavily overlapping skills."""
    pair_counts, per_skill_counts = _pair_session_overlap(sessions)
    cards = []

    by_name = {skill["name"]: skill for skill in catalog}
    for left_name, right_name in combinations(sorted(by_name), 2):
        left = by_name[left_name]
        right = by_name[right_name]
        discovery_sim = _jaccard(left["discovery_tokens"], right["discovery_tokens"])
        content_sim = _jaccard(left["content_tokens"], right["content_tokens"])
        name_sim = _jaccard(left["name_tokens"], right["name_tokens"])
        heading_bonus = 0.1 if left["heading"] == right["heading"] else 0.0
        similarity = (0.45 * discovery_sim) + (0.35 * content_sim) + (0.2 * name_sim) + heading_bonus
        shared_sessions = pair_counts.get((left_name, right_name), 0)
        overlap_rate = shared_sessions / max(1, per_skill_counts[left_name], per_skill_counts[right_name])
        has_structural_overlap = (
            discovery_sim >= 0.18
            or content_sim >= 0.45
            or name_sim >= 0.5
            or (left["heading"] == right["heading"] and content_sim >= 0.35)
        )
        if not has_structural_overlap:
            continue
        if similarity < 0.45:
            continue
        if overlap_rate < 0.25 and shared_sessions < 2:
            continue

        score = round((similarity * 42) + (overlap_rate * 26) + (shared_sessions * 3))
        if score < MIN_CARD_SCORE:
            continue

        canonical, legacy = _canonical_skill(left, right)
        modes_hint = left["has_modes"] or right["has_modes"]
        evidence = [
            {
                "timestamp": session["timestamp"],
                "signal": f"same request surface matched `{left_name}` and `{right_name}`",
                "user_request": session["user_request"],
            }
            for session in sessions
            if {left_name, right_name}.issubset(
                {
                    suggestion["skill"]
                    for suggestion in session.get("top_suggested_skills", [])
                    if suggestion["score"] >= DISCOVERABILITY_MIN_SCORE
                }
                | set(session.get("activated_skills", []))
            )
        ][:max_evidence]

        cards.append(
            {
                "issue_type": "skill-consolidation-opportunity",
                "score": score,
                "severity": "high" if similarity >= 0.75 else "medium",
                "scope": f"{left_name} + {right_name}",
                "affected_runs": shared_sessions,
                "total_runs": max(per_skill_counts[left_name], per_skill_counts[right_name], 1),
                "prevalence": round(overlap_rate, 3),
                "hypothesis": (
                    "Two skills have materially overlapping trigger surfaces and workflow content, "
                    "which raises maintenance cost and splits discoverability."
                ),
                "recommendation": (
                    (
                        f"Merge `{legacy}` into `{canonical}` and move project-specific literals into `modes/`; "
                        "keep the redundant skill as a thin alias or deprecation shim."
                    )
                    if modes_hint
                    else (
                        f"Consolidate `{left_name}` and `{right_name}` into one canonical skill, likely `{canonical}`, "
                        "and keep any true edge cases in references or subflows instead of parallel skills."
                    )
                ),
                "target_files": [left["path"], right["path"], "README.md"],
                "supporting_metrics": {
                    "metadata_similarity": round(similarity, 3),
                    "discovery_similarity": round(discovery_sim, 3),
                    "content_similarity": round(content_sim, 3),
                    "shared_surface_sessions": shared_sessions,
                },
                "evidence": evidence
                or [
                    {
                        "timestamp": "catalog",
                        "signal": (
                            f"shared heading `{left['heading']}` with similar descriptions "
                            f"(`{truncate(left['description'], 120)}` / `{truncate(right['description'], 120)}`)"
                        ),
                        "user_request": None,
                    }
                ],
                "followup_brief": (
                    f"Consolidate `{left_name}` and `{right_name}` around `{canonical}`. "
                    f"Shared surface sessions: {shared_sessions}."
                ),
            }
        )

    return cards


def generate_portfolio_opportunity_report(
    portfolio_report: dict[str, Any],
    min_cluster_runs: int = 2,
    max_cards: int = 12,
    max_evidence: int = 3,
) -> dict[str, Any]:
    """Generate ranked creation/discoverability/consolidation opportunity cards."""
    sessions = portfolio_report.get("sessions", [])
    catalog = portfolio_report.get("catalog", [])
    now = datetime.now(timezone.utc)
    cards = []
    cards.extend(
        _discoverability_cards(
            sessions=sessions,
            overall_runs=len(sessions),
            max_evidence=max_evidence,
            now=now,
        )
    )
    cards.extend(
        _creation_cards(
            sessions=sessions,
            overall_runs=len(sessions),
            min_cluster_runs=min_cluster_runs,
            max_evidence=max_evidence,
            now=now,
        )
    )
    cards.extend(
        _consolidation_cards(
            catalog=catalog,
            sessions=sessions,
            max_evidence=max_evidence,
        )
    )

    cards.sort(
        key=lambda card: (
            card["score"],
            card["prevalence"],
            card["affected_runs"],
        ),
        reverse=True,
    )

    issue_counts = Counter(card["issue_type"] for card in cards)
    return {
        "generated_at": now.isoformat(),
        "skills_root": portfolio_report.get("skills_root"),
        "source_review": {
            "generated_at": portfolio_report.get("generated_at"),
            "source": portfolio_report.get("source"),
            "since": portfolio_report.get("since"),
            "until": portfolio_report.get("until"),
            "sessions_scanned": portfolio_report.get("sessions_scanned"),
            "sessions_analyzed": portfolio_report.get("sessions_analyzed"),
            "providers": portfolio_report.get("providers", {}),
        },
        "catalog_summary": {
            "skills_loaded": portfolio_report.get("catalog_summary", {}).get("skills_loaded", len(catalog)),
        },
        "summary": {
            "cards_generated": len(cards),
            "cards_returned": min(len(cards), max_cards),
            "issue_types": dict(issue_counts),
        },
        "cards": cards[:max_cards],
    }


def render_portfolio_opportunity_markdown(report: dict[str, Any]) -> str:
    """Render a portfolio opportunity report as markdown."""
    source_review = report.get("source_review", {})
    catalog_summary = report.get("catalog_summary", {})
    cards = report.get("cards", [])

    lines = ["## Skill Portfolio Opportunity Funnel", ""]
    lines.append(
        "Uses transcript demand plus catalog overlap to rank when to create a new skill, "
        "improve discoverability, or consolidate overlapping skills."
    )
    lines.append("")
    lines.append(f"- Skills loaded: {catalog_summary.get('skills_loaded', 0)}")
    lines.append(f"- Sessions scanned: {source_review.get('sessions_scanned', 0)}")
    lines.append(f"- Sessions analyzed: {source_review.get('sessions_analyzed', 0)}")
    lines.append(f"- Cards returned: {len(cards)}")
    lines.append("")

    if not cards:
        lines.append("No portfolio opportunity cards met the scoring threshold.")
        return "\n".join(lines) + "\n"

    lines.append("| Rank | Score | Type | Scope | Runs | Prev |")
    lines.append("|------|-------|------|-------|------|------|")
    for idx, card in enumerate(cards, start=1):
        lines.append(
            f"| {idx} | {card['score']} | {card['issue_type']} | {card['scope']} | "
            f"{card['affected_runs']}/{card['total_runs']} | {card['prevalence']:.2f} |"
        )

    for idx, card in enumerate(cards, start=1):
        lines.append("")
        lines.append(f"### {idx}. {card['issue_type']} ({card['score']})")
        lines.append(f"Scope: `{card['scope']}`")
        lines.append(f"Why it matters: {card['hypothesis']}")
        lines.append(f"Suggested change: {card['recommendation']}")
        lines.append(f"Target files: {', '.join(card['target_files'])}")
        lines.append(f"Follow-up brief: {card['followup_brief']}")
        if card.get("supporting_metrics"):
            metrics = ", ".join(f"{key}={value}" for key, value in sorted(card["supporting_metrics"].items()))
            lines.append(f"Supporting metrics: {metrics}")
        lines.append("Evidence:")
        for evidence in card.get("evidence", []):
            request = evidence.get("user_request") or "n/a"
            lines.append(f"- {evidence.get('timestamp')} | {evidence.get('signal')} | {request}")

    return "\n".join(lines) + "\n"
