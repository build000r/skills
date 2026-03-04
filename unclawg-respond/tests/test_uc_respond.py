from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any


def _load_uc_respond():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "uc_respond"
    loader = importlib.machinery.SourceFileLoader("uc_respond_module", str(script_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def _msg(*, author_type: str, message_type: str, content: str, created_at: str, sequence: int, message_id: str = "") -> dict[str, object]:
    return {
        "id": message_id or f"msg-{sequence}",
        "author_type": author_type,
        "message_type": message_type,
        "content": content,
        "edited_content": None,
        "created_at": created_at,
        "sequence": sequence,
        "deleted_at": None,
    }


def _approval_detail(*, proposed_reply: str | None = None, summary: str | None = None, version: int = 3) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if proposed_reply is not None:
        payload["proposed_reply"] = proposed_reply
    if summary is not None:
        payload["summary"] = summary
    return {
        "context": {"payload": payload},
        "version": version,
        "status": "pending",
    }


def _revision(
    *,
    revision_id: str,
    status: str,
    created_at: str,
    trigger_message_ids: list[str] | None = None,
    fulfilled_message_id: str | None = None,
    terminal_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": revision_id,
        "approval_id": "apr-test",
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "trigger_message_ids": trigger_message_ids or [],
        "fulfilled_message_id": fulfilled_message_id,
        "terminal_reason": terminal_reason,
    }


def test_queue_decision_processes_soul_drift_without_feedback() -> None:
    uc = _load_uc_respond()
    messages = [
        _msg(
            author_type="machine",
            message_type="edit_diff",
            content="Updated suggestion under soul v7.",
            created_at="2026-03-01T17:00:00Z",
            sequence=10,
        ),
    ]

    decision = uc._queue_decision(messages, published_soul_version=8)

    assert decision.should_process is True
    assert decision.reason == "machine_soul_version_drift"


def test_queue_decision_processes_when_feedback_is_newer() -> None:
    uc = _load_uc_respond()
    messages = [
        _msg(
            author_type="machine",
            message_type="comment",
            content="Updated suggestion under soul v8.",
            created_at="2026-03-01T17:00:00Z",
            sequence=10,
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content="Please make this shorter.",
            created_at="2026-03-01T18:00:00Z",
            sequence=11,
        ),
    ]

    decision = uc._queue_decision(messages, published_soul_version=8)

    assert decision.should_process is True
    assert decision.reason == "feedback_newer_than_machine"


def test_queue_decision_processes_when_system_soul_update_is_newer() -> None:
    uc = _load_uc_respond()
    messages = [
        _msg(
            author_type="machine",
            message_type="edit_diff",
            content="Updated suggestion.",
            created_at="2026-03-01T17:00:00Z",
            sequence=10,
        ),
        _msg(
            author_type="system",
            message_type="system",
            content="soul updated to v8",
            created_at="2026-03-01T18:00:00Z",
            sequence=11,
        ),
    ]

    decision = uc._queue_decision(messages, published_soul_version=8)

    assert decision.should_process is True
    assert decision.reason == "soul_update_newer_than_machine"


def test_reconcile_prints_target_before_network_calls(monkeypatch, capsys) -> None:
    uc = _load_uc_respond()
    order: list[str] = []

    cfg = uc.Config(
        api_url="http://localhost:8010",
        tenant_id="tenant-dev",
        machine_key_id="mk_test",
        machine_secret="ms_test",
        agent_id="larry",
        api_key=None,
    )

    monkeypatch.setattr(uc, "resolve_config", lambda _: cfg)

    def _print_target(_cfg):
        order.append("print")
        print(f"target api_url={_cfg.api_url} tenant_id={_cfg.tenant_id} agent_id={_cfg.agent_id}")

    monkeypatch.setattr(uc, "_print_target", _print_target)
    monkeypatch.setattr(uc, "_load_published_soul_snapshot", lambda _: uc.SoulSnapshot(version=None, content=""))
    monkeypatch.setattr(uc, "_fetch_pending_approvals", lambda _: [])
    monkeypatch.setattr(uc, "_fetch_all_agent_revisions", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(uc, "_request_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected network call")))

    rc = uc.cmd_reconcile(argparse.Namespace(agent_id="larry", dry_run=True))
    stdout = capsys.readouterr().out.splitlines()

    assert rc == 0
    assert order[0] == "print"
    assert stdout[0] == "target api_url=http://localhost:8010 tenant_id=tenant-dev agent_id=larry"


def test_load_agent_env_reads_openclaw_state_dir(monkeypatch, tmp_path) -> None:
    uc = _load_uc_respond()
    state_dir = tmp_path / "openclaw-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / ".env").write_text(
        "OPENCLAW_API_URL=https://api.unclawg.com\n"
        "OPENCLAW_TENANT_ID=tenant-dev\n"
        "OPENCLAW_MACHINE_KEY_ID=mk_test\n"
        "OPENCLAW_MACHINE_SECRET=ms_test\n"
        "OPENCLAW_AGENT_ID=larry\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENCLAW_API_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_TENANT_ID", raising=False)
    monkeypatch.delenv("OPENCLAW_MACHINE_KEY_ID", raising=False)
    monkeypatch.delenv("OPENCLAW_MACHINE_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_AGENT_ID", raising=False)
    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(state_dir))

    uc._load_agent_env(None)

    assert os.environ["OPENCLAW_API_URL"] == "https://api.unclawg.com"
    assert os.environ["OPENCLAW_TENANT_ID"] == "tenant-dev"
    assert os.environ["OPENCLAW_MACHINE_KEY_ID"] == "mk_test"
    assert os.environ["OPENCLAW_MACHINE_SECRET"] == "ms_test"
    assert os.environ["OPENCLAW_AGENT_ID"] == "larry"


def test_load_agent_env_overwrites_inherited_vars_from_larry_env(monkeypatch, tmp_path) -> None:
    uc = _load_uc_respond()
    larry_env = tmp_path / "larry.env"
    larry_env.write_text(
        "OPENCLAW_API_URL=https://api.unclawg.com\n"
        "OPENCLAW_TENANT_ID=tenant-correct\n"
        "OPENCLAW_MACHINE_KEY_ID=mk_correct\n"
        "OPENCLAW_MACHINE_SECRET=ms_correct\n"
        "OPENCLAW_AGENT_ID=larry\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("LARRY_ENV_PATH", str(larry_env))
    monkeypatch.setenv("OPENCLAW_API_URL", "https://wrong.example.com")
    monkeypatch.setenv("OPENCLAW_TENANT_ID", "tenant-wrong")
    monkeypatch.setenv("OPENCLAW_MACHINE_KEY_ID", "mk_wrong")
    monkeypatch.setenv("OPENCLAW_MACHINE_SECRET", "ms_wrong")
    monkeypatch.setenv("OPENCLAW_AGENT_ID", "other-agent")

    uc._load_agent_env("larry")

    assert os.environ["OPENCLAW_API_URL"] == "https://api.unclawg.com"
    assert os.environ["OPENCLAW_TENANT_ID"] == "tenant-correct"
    assert os.environ["OPENCLAW_MACHINE_KEY_ID"] == "mk_correct"
    assert os.environ["OPENCLAW_MACHINE_SECRET"] == "ms_correct"
    assert os.environ["OPENCLAW_AGENT_ID"] == "larry"


def test_build_fulfillment_payload_uses_latest_feedback_and_end_with_directive() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "Honest answer: founders keep final judgment while AI drafts. "
            "It saves time and keeps decisions human."
        )
    )
    messages = [
        _msg(
            author_type="human",
            message_type="feedback",
            content="Add more hype and end with: comment below for the playbook.",
            created_at="2026-03-03T11:00:00Z",
            sequence=1,
            message_id="msg-old",
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content="Make this tighter and end with: DM me and I will share the exact workflow.",
            created_at="2026-03-03T12:00:00Z",
            sequence=2,
            message_id="msg-new",
        ),
    ]
    revision = _revision(revision_id="rev-1", status="pending", created_at="2026-03-03T12:01:00Z", trigger_message_ids=["msg-new"])

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-1",
        expected_version=3,
        latest_feedback=messages[-1],
        approval_detail=detail,
        soul_version=9,
        messages=messages,
        revision=revision,
        revision_history=[revision],
    )

    assert message_type == "edit_diff"
    assert action_kind == "edit_diff"
    assert payload["edited_content"].rstrip().endswith("DM me and I will share the exact workflow.")
    assert "comment below for the playbook" not in payload["edited_content"]


def test_build_fulfillment_payload_has_no_default_cta_injection() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "Founders handle approvals while AI drafts suggestions. "
            "This keeps decisions human while reducing typing."
        )
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Tighten this and remove fluff.",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-2", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-2",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=9,
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    assert message_type == "edit_diff"
    assert action_kind == "edit_diff"
    assert "DM me if you want the exact workflow." not in payload["edited_content"]


def test_build_fulfillment_payload_ambiguous_feedback_returns_clarifying_comment() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(proposed_reply="I can share the framework if helpful.")
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="idk about this",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-3", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-3",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=9,
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    assert message_type == "comment"
    assert action_kind == "clarification"
    assert "Need clarification" in payload["content"]
    assert "edited_content" not in payload


def test_build_fulfillment_payload_deny_recommendation_requires_high_confidence_signal() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(proposed_reply="Here is a draft reply.")
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Please deny this. It is unsafe and deceptive.",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-4", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-4",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=9,
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    assert message_type == "comment"
    assert action_kind == "deny_recommendation"
    assert "Recommend deny" in payload["content"]
    assert "edited_content" not in payload


def test_build_fulfillment_payload_deny_negation_does_not_trigger_deny() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(proposed_reply="Original reply text with two lines. Keep final approval human.")
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Don't deny this. Just make it tighter.",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-5", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-5",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=9,
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    assert action_kind != "deny_recommendation"
    assert message_type == "edit_diff"
    assert payload["message_type"] == "edit_diff"


def test_build_revision_context_includes_ordered_thread_and_prior_revision_outcomes() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(proposed_reply="Original")
    messages = [
        _msg(
            author_type="machine",
            message_type="edit_diff",
            content="Earlier machine draft",
            created_at="2026-03-03T11:00:00Z",
            sequence=2,
            message_id="m2",
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content="Latest feedback",
            created_at="2026-03-03T12:00:00Z",
            sequence=1,
            message_id="m1",
        ),
    ]
    current_revision = _revision(revision_id="rev-current", status="pending", created_at="2026-03-03T12:01:00Z", trigger_message_ids=["m1"])
    prior_revision = _revision(
        revision_id="rev-old",
        status="fulfilled",
        created_at="2026-03-03T10:00:00Z",
        fulfilled_message_id="machine-msg-1",
    )

    bundle = uc._build_revision_context(
        "apr-test",
        detail,
        messages=messages,
        revision=current_revision,
        revision_history=[current_revision, prior_revision],
        soul_snapshot=uc.SoulSnapshot(version=11, content="No exclamation."),
    )

    assert [item["id"] for item in bundle["thread_messages"]] == ["m2", "m1"]
    assert bundle["trigger_message_ids"] == ["m1"]
    assert [item["id"] for item in bundle["revision_outcomes"]] == ["rev-old", "rev-current"]
    assert bundle["revision_outcomes"][0]["fulfilled_message_id"] == "machine-msg-1"
    assert bundle["revision_outcomes"][1]["is_current"] is True


def test_build_fulfillment_payload_sets_content_vs_edited_content_contract() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "Founders keep final judgment while AI drafts to save time. "
            "The process keeps output fast and accountable."
        )
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Make this tighter.",
        created_at="2026-03-03T12:00:00Z",
        sequence=1,
    )
    revision = _revision(revision_id="rev-6", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, _ = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-6",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=9,
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    assert message_type == "edit_diff"
    assert payload["content"].startswith("Revised draft")
    assert len(payload["content"]) <= 80
    assert payload["edited_content"] != payload["content"]


def test_build_fulfillment_payload_strips_markers_and_concat_artifacts() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "Base reply line. [Reconciled under soul v2] Feedback addressed: remove marker tail"
        )
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Make this tighter and end with: DM me and I will share the exact workflow.",
        created_at="2026-03-03T12:00:00Z",
        sequence=1,
    )
    revision = _revision(revision_id="rev-7", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, _, _ = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-7",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=9,
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    edited = payload["edited_content"]
    assert "[Reconciled under soul" not in edited
    assert "Feedback addressed:" not in edited
    assert "end with:" not in edited.lower()
    assert uc._normalize_for_compare(edited) != uc._normalize_for_compare("Base reply line.")


def test_build_fulfillment_payload_applies_latest_soul_rules() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply="Big update! #AI founders keep judgment while AI drafts."
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Make this tighter.",
        created_at="2026-03-03T12:00:00Z",
        sequence=1,
    )
    revision = _revision(revision_id="rev-8", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, _ = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-8",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=12,
        soul_text="No hashtags. One sentence. No exclamation.",
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    assert message_type == "edit_diff"
    assert "#" not in payload["edited_content"]
    assert "!" not in payload["edited_content"]
    assert len(uc._split_sentences(payload["edited_content"])) == 1


def test_reconcile_deny_path_uses_message_fulfill_and_not_decisions(monkeypatch) -> None:
    uc = _load_uc_respond()
    cfg = uc.Config(
        api_url="http://localhost:8010",
        tenant_id="tenant-dev",
        machine_key_id="mk_test",
        machine_secret="ms_test",
        agent_id="larry",
        api_key=None,
    )
    requests: list[tuple[str, str]] = []

    monkeypatch.setattr(uc, "resolve_config", lambda _: cfg)
    monkeypatch.setattr(uc, "_print_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(uc, "_load_published_soul_snapshot", lambda _cfg: uc.SoulSnapshot(version=7, content=""))
    monkeypatch.setattr(uc, "_fetch_pending_approvals", lambda _cfg: [{"id": "apr-1"}])

    def _fetch_revisions(_cfg, status, limit=200):
        if status == "pending":
            return [{"id": "rev-1", "approval_id": "apr-1", "status": "pending", "created_at": "2026-03-03T12:01:00Z"}]
        return []

    monkeypatch.setattr(uc, "_fetch_all_agent_revisions", _fetch_revisions)
    monkeypatch.setattr(
        uc,
        "_fetch_messages",
        lambda _cfg, _approval_id: [
            _msg(
                author_type="human",
                message_type="feedback",
                content="Please deny this. It is unsafe and deceptive.",
                created_at="2026-03-03T12:00:00Z",
                sequence=1,
                message_id="f1",
            )
        ],
    )

    def _request_json(_cfg, method, path, **kwargs):
        requests.append((method, path))
        if method == "GET" and path == "/v0/approval-requests/apr-1":
            return {"data": _approval_detail(proposed_reply="Draft text.", version=3)}
        if method == "POST" and path == "/v0/approval-requests/apr-1/messages/fulfill":
            return {"data": {"id": "msg-1"}}
        raise AssertionError(f"unexpected request: {method} {path} {kwargs}")

    monkeypatch.setattr(uc, "_request_json", _request_json)

    rc = uc.cmd_reconcile(argparse.Namespace(agent_id="larry", dry_run=False))

    assert rc == 0
    assert any(path.endswith("/messages/fulfill") for _, path in requests)
    assert all("/decisions" not in path for _, path in requests)


def test_build_fulfillment_payload_missing_seed_and_weak_feedback_clarifies() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(proposed_reply=None, summary=None)
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="hmm",
        created_at="2026-03-03T12:00:00Z",
        sequence=1,
    )
    revision = _revision(revision_id="rev-9", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-9",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=9,
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    assert message_type == "comment"
    assert action_kind == "clarification"
    assert "Need clarification" in payload["content"]
