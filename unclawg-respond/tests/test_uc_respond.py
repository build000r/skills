from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
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


def _msg(
    *,
    author_type: str,
    message_type: str,
    content: str,
    created_at: str,
    sequence: int,
    message_id: str = "",
    edited_content: str | None = None,
) -> dict[str, object]:
    return {
        "id": message_id or f"msg-{sequence}",
        "author_type": author_type,
        "message_type": message_type,
        "content": content,
        "edited_content": edited_content,
        "created_at": created_at,
        "sequence": sequence,
        "deleted_at": None,
    }


def _approval_detail(
    *,
    proposed_reply: str | None = None,
    summary: str | None = None,
    version: int = 3,
    context_type: str | None = None,
    payload_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if proposed_reply is not None:
        payload["proposed_reply"] = proposed_reply
    if summary is not None:
        payload["summary"] = summary
    if payload_extras:
        payload.update(payload_extras)
    context: dict[str, Any] = {"payload": payload}
    if context_type is not None:
        context["context_type"] = context_type
    return {
        "context": context,
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
        agent_id="example-agent",
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

    rc = uc.cmd_reconcile(argparse.Namespace(agent_id="example-agent", dry_run=True))
    stdout = capsys.readouterr().out.splitlines()

    assert rc == 0
    assert order[0] == "print"
    assert stdout[0] == "target api_url=http://localhost:8010 tenant_id=tenant-dev agent_id=example-agent"


def test_canary_dry_run_builds_single_approval_payload(monkeypatch, capsys) -> None:
    uc = _load_uc_respond()
    cfg = uc.Config(
        api_url="http://localhost:8010",
        tenant_id="tenant-dev",
        machine_key_id="mk_test",
        machine_secret="ms_test",
        agent_id="example-agent",
        api_key=None,
    )

    monkeypatch.setattr(uc, "resolve_config", lambda _: cfg)
    monkeypatch.setattr(uc, "_print_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(uc, "_safe_load_published_soul_snapshot", lambda _cfg: uc.SoulSnapshot(version=7, content=""))
    monkeypatch.setattr(
        uc,
        "_fetch_messages",
        lambda _cfg, _approval_id: [
            _msg(
                author_type="human",
                message_type="feedback",
                content="Make this tighter.",
                created_at="2026-03-03T12:00:00Z",
                sequence=1,
            )
        ],
    )
    monkeypatch.setattr(
        uc,
        "_load_revision_map",
        lambda _cfg: {
            "apr-1": [
                _revision(
                    revision_id="rev-1",
                    status="pending",
                    created_at="2026-03-03T12:01:00Z",
                )
            ]
        },
    )
    monkeypatch.setattr(
        uc,
        "_request_json",
        lambda _cfg, method, path, **_kwargs: {"data": _approval_detail(proposed_reply="Draft text.", version=3)}
        if method == "GET" and path == "/v0/approval-requests/apr-1"
        else (_ for _ in ()).throw(AssertionError(f"unexpected request: {method} {path}")),
    )

    rc = uc.cmd_canary(
        argparse.Namespace(
            agent_id="example-agent",
            approval_id="apr-1",
            revision_id=None,
            dry_run=True,
            force=False,
        )
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["approval_id"] == "apr-1"
    assert payload["revision_id"] == "rev-1"
    assert payload["action"] == "dry_run"
    assert payload["message_type"] == "edit_diff"
    assert payload["forced"] is False
    assert payload["payload"]["revision_request_id"] == "rev-1"


def test_canary_skips_not_queued_without_force(monkeypatch, capsys) -> None:
    uc = _load_uc_respond()
    cfg = uc.Config(
        api_url="http://localhost:8010",
        tenant_id="tenant-dev",
        machine_key_id="mk_test",
        machine_secret="ms_test",
        agent_id="example-agent",
        api_key=None,
    )

    monkeypatch.setattr(uc, "resolve_config", lambda _: cfg)
    monkeypatch.setattr(uc, "_print_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(uc, "_safe_load_published_soul_snapshot", lambda _cfg: uc.SoulSnapshot(version=7, content=""))
    monkeypatch.setattr(
        uc,
        "_fetch_messages",
        lambda _cfg, _approval_id: [
            _msg(
                author_type="human",
                message_type="feedback",
                content="Make this tighter.",
                created_at="2026-03-03T12:00:00Z",
                sequence=1,
            ),
            _msg(
                author_type="machine",
                message_type="edit_diff",
                content="Revised draft under soul v7.",
                edited_content="Tighter draft.",
                created_at="2026-03-03T12:01:00Z",
                sequence=2,
            ),
        ],
    )
    monkeypatch.setattr(
        uc,
        "_load_revision_map",
        lambda _cfg: (_ for _ in ()).throw(AssertionError("revision map should not load when canary is skipped")),
    )
    monkeypatch.setattr(
        uc,
        "_request_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected request")),
    )

    rc = uc.cmd_canary(
        argparse.Namespace(
            agent_id="example-agent",
            approval_id="apr-1",
            revision_id=None,
            dry_run=True,
            force=False,
        )
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload == {
        "approval_id": "apr-1",
        "action": "skip_not_queued",
        "reason": "up_to_date",
        "forced": False,
    }


def test_canary_force_dry_run_rebuilds_up_to_date_card(monkeypatch, capsys) -> None:
    uc = _load_uc_respond()
    cfg = uc.Config(
        api_url="http://localhost:8010",
        tenant_id="tenant-dev",
        machine_key_id="mk_test",
        machine_secret="ms_test",
        agent_id="example-agent",
        api_key=None,
    )

    monkeypatch.setattr(uc, "resolve_config", lambda _: cfg)
    monkeypatch.setattr(uc, "_print_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(uc, "_safe_load_published_soul_snapshot", lambda _cfg: uc.SoulSnapshot(version=8, content=""))
    monkeypatch.setattr(
        uc,
        "_fetch_messages",
        lambda _cfg, _approval_id: [
            _msg(
                author_type="human",
                message_type="feedback",
                content="Make this tighter.",
                created_at="2026-03-03T12:00:00Z",
                sequence=1,
            ),
            _msg(
                author_type="machine",
                message_type="edit_diff",
                content="Revised draft under soul v8.",
                edited_content="Tighter draft.",
                created_at="2026-03-03T12:01:00Z",
                sequence=2,
            ),
        ],
    )
    monkeypatch.setattr(
        uc,
        "_load_revision_map",
        lambda _cfg: {
            "apr-1": [
                _revision(
                    revision_id="rev-1",
                    status="pending",
                    created_at="2026-03-03T12:02:00Z",
                )
            ]
        },
    )
    monkeypatch.setattr(
        uc,
        "_request_json",
        lambda _cfg, method, path, **_kwargs: {"data": _approval_detail(proposed_reply="Draft text.", version=3)}
        if method == "GET" and path == "/v0/approval-requests/apr-1"
        else (_ for _ in ()).throw(AssertionError(f"unexpected request: {method} {path}")),
    )

    rc = uc.cmd_canary(
        argparse.Namespace(
            agent_id="example-agent",
            approval_id="apr-1",
            revision_id=None,
            dry_run=True,
            force=True,
        )
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["approval_id"] == "apr-1"
    assert payload["action"] == "dry_run"
    assert payload["reason"] == "up_to_date"
    assert payload["forced"] is True
    assert payload["payload"]["revision_request_id"] == "rev-1"


def test_load_agent_env_reads_openclaw_state_dir(monkeypatch, tmp_path) -> None:
    uc = _load_uc_respond()
    state_dir = tmp_path / "openclaw-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / ".env").write_text(
        "OPENCLAW_API_URL=https://api.example.com\n"
        "OPENCLAW_TENANT_ID=tenant-dev\n"
        "OPENCLAW_MACHINE_KEY_ID=mk_test\n"
        "OPENCLAW_MACHINE_SECRET=ms_test\n"
        "OPENCLAW_AGENT_ID=example-agent\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENCLAW_API_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_TENANT_ID", raising=False)
    monkeypatch.delenv("OPENCLAW_MACHINE_KEY_ID", raising=False)
    monkeypatch.delenv("OPENCLAW_MACHINE_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_AGENT_ID", raising=False)
    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(state_dir))

    uc._load_agent_env(None)

    assert os.environ["OPENCLAW_API_URL"] == "https://api.example.com"
    assert os.environ["OPENCLAW_TENANT_ID"] == "tenant-dev"
    assert os.environ["OPENCLAW_MACHINE_KEY_ID"] == "mk_test"
    assert os.environ["OPENCLAW_MACHINE_SECRET"] == "ms_test"
    assert os.environ["OPENCLAW_AGENT_ID"] == "example-agent"


def test_load_agent_env_overwrites_inherited_vars_from_explicit_runtime_env(monkeypatch, tmp_path) -> None:
    uc = _load_uc_respond()
    runtime_env = tmp_path / "agent.env"
    runtime_env.write_text(
        "OPENCLAW_API_URL=https://api.example.com\n"
        "OPENCLAW_TENANT_ID=tenant-correct\n"
        "OPENCLAW_MACHINE_KEY_ID=mk_correct\n"
        "OPENCLAW_MACHINE_SECRET=ms_correct\n"
        "OPENCLAW_AGENT_ID=agent-one\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENCLAW_ENV_PATH", str(runtime_env))
    monkeypatch.setenv("OPENCLAW_API_URL", "https://wrong.example.com")
    monkeypatch.setenv("OPENCLAW_TENANT_ID", "tenant-wrong")
    monkeypatch.setenv("OPENCLAW_MACHINE_KEY_ID", "mk_wrong")
    monkeypatch.setenv("OPENCLAW_MACHINE_SECRET", "ms_wrong")
    monkeypatch.setenv("OPENCLAW_AGENT_ID", "other-agent")

    uc._load_agent_env("agent-one")

    assert os.environ["OPENCLAW_API_URL"] == "https://api.example.com"
    assert os.environ["OPENCLAW_TENANT_ID"] == "tenant-correct"
    assert os.environ["OPENCLAW_MACHINE_KEY_ID"] == "mk_correct"
    assert os.environ["OPENCLAW_MACHINE_SECRET"] == "ms_correct"
    assert os.environ["OPENCLAW_AGENT_ID"] == "agent-one"


def test_load_agent_env_reads_single_agent_env_from_state_dir(monkeypatch, tmp_path) -> None:
    uc = _load_uc_respond()
    state_dir = tmp_path / "openclaw-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "agent-one.env").write_text(
        "OPENCLAW_API_URL=https://api.example.com\n"
        "OPENCLAW_TENANT_ID=tenant-dev\n"
        "OPENCLAW_MACHINE_KEY_ID=mk_test\n"
        "OPENCLAW_MACHINE_SECRET=ms_test\n"
        "OPENCLAW_AGENT_ID=agent-one\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("OPENCLAW_API_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_TENANT_ID", raising=False)
    monkeypatch.delenv("OPENCLAW_MACHINE_KEY_ID", raising=False)
    monkeypatch.delenv("OPENCLAW_MACHINE_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_AGENT_ID", raising=False)
    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(state_dir))

    uc._load_agent_env(None)

    assert os.environ["OPENCLAW_API_URL"] == "https://api.example.com"
    assert os.environ["OPENCLAW_TENANT_ID"] == "tenant-dev"
    assert os.environ["OPENCLAW_MACHINE_KEY_ID"] == "mk_test"
    assert os.environ["OPENCLAW_MACHINE_SECRET"] == "ms_test"
    assert os.environ["OPENCLAW_AGENT_ID"] == "agent-one"


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


def test_build_fulfillment_payload_uses_prior_machine_edit_history_in_rewrite() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply="Original seed that should not be reused as the rewrite baseline."
    )
    messages = [
        _msg(
            author_type="machine",
            message_type="edit_diff",
            content="First revision",
            edited_content=(
                "Current draft: founders keep final approval while AI drafts the first pass. "
                "This keeps quality high."
            ),
            created_at="2026-03-03T11:00:00Z",
            sequence=1,
            message_id="m1",
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content="Shorten this.",
            created_at="2026-03-03T12:00:00Z",
            sequence=2,
            message_id="f1",
        ),
    ]
    revision = _revision(revision_id="rev-ctx", status="pending", created_at="2026-03-03T12:01:00Z", trigger_message_ids=["f1"])

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-ctx",
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
    assert payload["edited_content"].startswith("Current draft:")
    assert "Original seed that should not be reused" not in payload["edited_content"]


def test_build_revision_context_preserves_long_prior_edit_without_truncation() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(proposed_reply="Seed text.")
    long_prior = ("A" * 1200) + " THE_END_MARKER"
    messages = [
        _msg(
            author_type="machine",
            message_type="edit_diff",
            content="old",
            edited_content=long_prior,
            created_at="2026-03-03T11:00:00Z",
            sequence=1,
            message_id="m-long",
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content="Shorten this.",
            created_at="2026-03-03T12:00:00Z",
            sequence=2,
            message_id="f1",
        ),
    ]
    revision = _revision(revision_id="rev-long", status="pending", created_at="2026-03-03T12:01:00Z", trigger_message_ids=["f1"])

    bundle = uc._build_revision_context(
        "apr-test",
        detail,
        messages=messages,
        revision=revision,
        revision_history=[revision],
        soul_snapshot=uc.SoulSnapshot(version=9, content=""),
    )

    assert bundle["latest_prior_edit_text"].endswith("THE_END_MARKER")
    assert len(bundle["latest_prior_edit_text"]) > 1200
    assert bundle["prior_machine_messages"][0]["edited_content"].endswith("THE_END_MARKER")


def test_build_fulfillment_payload_synthesizes_multi_turn_feedback_semantics() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "Hype mode: our AI crushes it for outbound. "
            "The founder still approves the final publish."
        )
    )
    messages = [
        _msg(
            author_type="human",
            message_type="feedback",
            content="Mention approval queue and keep this conversational.",
            created_at="2026-03-03T10:00:00Z",
            sequence=1,
            message_id="f1",
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content=(
                "Actually keep it professional. Remove hype mode and replace crushes it "
                "with drafts first-pass replies."
            ),
            created_at="2026-03-03T11:00:00Z",
            sequence=2,
            message_id="f2",
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content="End with: DM for the exact workflow.",
            created_at="2026-03-03T12:00:00Z",
            sequence=3,
            message_id="f3",
        ),
    ]
    revision = _revision(revision_id="rev-sem", status="pending", created_at="2026-03-03T12:01:00Z", trigger_message_ids=["f3"])

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-sem",
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
    edited = payload["edited_content"]
    assert "approval queue" in edited.lower()
    assert "hype mode" not in edited.lower()
    assert "drafts first-pass replies" in edited
    assert edited.rstrip().endswith("DM for the exact workflow.")


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


def test_build_fulfillment_payload_short_actionable_feedback_rewrites_not_clarifies() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "Founders keep final approval while AI drafts. "
            "This removes busywork from daily replies."
        )
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Shorten this.",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-shorten", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-shorten",
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
    assert "Need clarification" not in payload["content"]


def test_build_fulfillment_payload_update_per_new_soul_generates_edit_diff() -> None:
    uc = _load_uc_respond()
    baseline = (
        "Founders keep final approval while AI drafts initial replies. "
        "The approval queue is where judgment still matters."
    )
    detail = _approval_detail(proposed_reply=baseline)
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="update per new soul",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-soul", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-soul",
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
    assert "Need clarification" not in payload["content"]
    assert uc._normalize_for_compare(payload["edited_content"]) != uc._normalize_for_compare(baseline)


def test_build_fulfillment_payload_social_uses_context_dump_model_output(monkeypatch) -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply="Founders keep approvals while AI drafts.",
        context_type="social_reply",
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Please rewrite this with clearer framing.",
        created_at="2026-03-05T06:58:00Z",
        sequence=3,
        message_id="msg-social",
    )
    revision = _revision(
        revision_id="rev-social-context",
        status="pending",
        created_at="2026-03-05T07:00:00Z",
        trigger_message_ids=["msg-social"],
    )

    monkeypatch.setattr(uc, "_call_social_rewrite_model", lambda _dump: "Model rewrite output.")
    monkeypatch.setattr(
        uc,
        "_force_material_rewrite",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fallback should not run when model returns content")),
    )

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-21856dbdd4",
        revision_id="rev-social-context",
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
    assert payload["edited_content"] == "Model rewrite output."


def test_build_fulfillment_payload_social_context_dump_uses_latest_feedback_comment(monkeypatch) -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply="Seed social draft.",
        summary="A clearer explanation should beat hype.",
        context_type="social_reply",
        payload_extras={
            "source_post": {
                "text": "Prediction markets only work when the process is disciplined.",
                "url": "https://x.example/post/1",
                "author": "@disciplineposter",
            }
        },
    )
    older_feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="older feedback",
        created_at="2026-03-05T06:40:00Z",
        sequence=2,
        message_id="msg-old",
    )
    latest_comment = _msg(
        author_type="human",
        message_type="comment",
        content="latest comment should drive rewrite",
        created_at="2026-03-05T06:58:00Z",
        sequence=3,
        message_id="msg-new",
    )
    revision = _revision(
        revision_id="rev-social-context-latest",
        status="pending",
        created_at="2026-03-05T07:00:00Z",
        trigger_message_ids=["msg-new"],
    )

    captured_dump: dict[str, Any] = {}

    def _capture_model(context_dump: dict[str, Any]) -> str:
        captured_dump.update(context_dump)
        return "model output from dump"

    monkeypatch.setattr(uc, "_call_social_rewrite_model", _capture_model)

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-21856dbdd4",
        revision_id="rev-social-context-latest",
        expected_version=3,
        latest_feedback=latest_comment,
        approval_detail=detail,
        soul_version=9,
        messages=[older_feedback, latest_comment],
        revision=revision,
        revision_history=[revision],
    )

    assert message_type == "edit_diff"
    assert action_kind == "edit_diff"
    assert payload["edited_content"] == "model output from dump"
    assert captured_dump["latest_feedback_text"] == "latest comment should drive rewrite"
    assert captured_dump["feedback_history"][-1]["content"] == "latest comment should drive rewrite"
    assert captured_dump["trigger_message_ids"] == ["msg-new"]
    assert isinstance(captured_dump["revision_outcomes"], list)
    assert captured_dump["target_draft_text"] == "Seed social draft."
    assert captured_dump["approval_summary"] == "A clearer explanation should beat hype."
    assert captured_dump["source_post_text"] == "Prediction markets only work when the process is disciplined."
    assert captured_dump["source_post_author"] == "@disciplineposter"
    assert captured_dump["rewrite_markers"]["return_format"] == "reply_text_only"
    assert "<<TASK>>" in captured_dump["rewrite_brief"]
    assert "<<LATEST_FEEDBACK>>" in captured_dump["rewrite_brief"]
    assert "latest comment should drive rewrite" in captured_dump["rewrite_brief"]


def test_build_fulfillment_payload_deadpan_feedback_generates_material_rewrite() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "Autonomous marketing agents can run campaigns all night. "
            "The hard part is keeping public output on-brand when no one is awake."
        )
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Make this funnier and deadpan, sarcastic tone.",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-deadpan", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-deadpan",
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
    assert payload["edited_content"].startswith("Deadpan take:")


def test_build_fulfillment_payload_non_social_ambiguous_feedback_returns_clarification() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply="I can share the framework if helpful.",
        context_type="trade_action",
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="ok?",
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


def test_build_fulfillment_payload_social_short_feedback_still_returns_edit_diff(monkeypatch) -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "\"Who use it properly\" is doing a lot of heavy lifting here lol. "
            "My agent used prediction markets very improperly at 3am once."
        ),
        context_type="social_reply",
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="thats quite a prediction",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-social-short", status="pending", created_at="2026-03-03T12:01:00Z")
    monkeypatch.setattr(uc, "_call_social_rewrite_model", lambda _dump: "social rewrite short")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-social-short",
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
    assert payload["edited_content"]
    assert payload["edited_content"] == "social rewrite short"


def test_build_fulfillment_payload_social_one_liner_feedback_returns_edit_diff(monkeypatch) -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply="We had a similar thing — the prompt said do not act, but the agent still posted.",
        context_type="social_reply",
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="llama 4?",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-social-one-liner", status="pending", created_at="2026-03-03T12:01:00Z")
    monkeypatch.setattr(uc, "_call_social_rewrite_model", lambda _dump: "social rewrite one liner")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-social-one-liner",
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
    assert payload["edited_content"] == "social rewrite one liner"


def test_build_fulfillment_payload_social_empty_rewrite_returns_clarification(monkeypatch) -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "\"Who use it properly\" is doing a lot of heavy lifting here lol. "
            "My agent used prediction markets very improperly at 3am once."
        ),
        context_type="social_reply",
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="thats quite a prediction",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-social-empty", status="pending", created_at="2026-03-03T12:01:00Z")
    monkeypatch.setattr(uc, "_call_social_rewrite_model", lambda _dump: "")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-social-empty",
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


def test_build_fulfillment_payload_social_feedback_echo_returns_clarification(monkeypatch) -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(
        proposed_reply=(
            "\"Who use it properly\" is doing a lot of heavy lifting here lol. "
            "My agent used prediction markets very improperly at 3am once."
        ),
        context_type="social_reply",
    )
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="thats quite a prediction",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-social-echo", status="pending", created_at="2026-03-03T12:01:00Z")
    monkeypatch.setattr(uc, "_call_social_rewrite_model", lambda _dump: "thats quite a prediction")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-social-echo",
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


def test_queue_decision_uses_human_comment_as_feedback_signal() -> None:
    uc = _load_uc_respond()
    messages = [
        _msg(
            author_type="human",
            message_type="comment",
            content="Tighten this one.",
            created_at="2026-03-03T12:00:00Z",
            sequence=1,
        )
    ]

    decision = uc._queue_decision(messages, published_soul_version=8)

    assert decision.should_process is True
    assert decision.reason == "no_machine_response"
    assert decision.latest_feedback is not None
    assert decision.latest_feedback.get("message_type") == "comment"


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


def test_build_fulfillment_payload_plain_deny_directive_is_not_high_confidence() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(proposed_reply="Here is a draft reply.")
    feedback = _msg(
        author_type="human",
        message_type="feedback",
        content="Please deny this.",
        created_at="2026-03-03T12:00:00Z",
        sequence=2,
    )
    revision = _revision(revision_id="rev-plain-deny", status="pending", created_at="2026-03-03T12:01:00Z")

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-plain-deny",
        expected_version=3,
        latest_feedback=feedback,
        approval_detail=detail,
        soul_version=9,
        messages=[feedback],
        revision=revision,
        revision_history=[revision],
    )

    assert action_kind != "deny_recommendation"
    assert message_type == "comment"
    assert "Recommend deny" not in payload["content"]


def test_build_fulfillment_payload_deny_confidence_uses_history_signals() -> None:
    uc = _load_uc_respond()
    detail = _approval_detail(proposed_reply="Here is a draft reply.")
    messages = [
        _msg(
            author_type="human",
            message_type="feedback",
            content="This is deceptive and harmful.",
            created_at="2026-03-03T10:00:00Z",
            sequence=1,
            message_id="f1",
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content="Still unsafe and illegal for policy reasons.",
            created_at="2026-03-03T11:00:00Z",
            sequence=2,
            message_id="f2",
        ),
        _msg(
            author_type="human",
            message_type="feedback",
            content="Please deny this for policy violation.",
            created_at="2026-03-03T12:00:00Z",
            sequence=3,
            message_id="f3",
        ),
    ]
    prior_risk_revision = _revision(
        revision_id="rev-old-risk",
        status="failed",
        created_at="2026-03-03T09:00:00Z",
        terminal_reason="unsafe policy risk",
    )
    current_revision = _revision(
        revision_id="rev-risk-now",
        status="pending",
        created_at="2026-03-03T12:01:00Z",
        trigger_message_ids=["f3"],
    )

    payload, message_type, action_kind = uc._build_fulfillment_payload(
        approval_id="apr-test",
        revision_id="rev-risk-now",
        expected_version=3,
        latest_feedback=messages[-1],
        approval_detail=detail,
        soul_version=9,
        messages=messages,
        revision=current_revision,
        revision_history=[prior_risk_revision, current_revision],
    )

    assert message_type == "comment"
    assert action_kind == "deny_recommendation"
    assert "confidence" in payload["content"]


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
        agent_id="example-agent",
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

    rc = uc.cmd_reconcile(argparse.Namespace(agent_id="example-agent", dry_run=False))

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
