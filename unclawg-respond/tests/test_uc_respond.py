from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import sys
from pathlib import Path


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


def _msg(*, author_type: str, message_type: str, content: str, created_at: str, sequence: int) -> dict[str, object]:
    return {
        "author_type": author_type,
        "message_type": message_type,
        "content": content,
        "created_at": created_at,
        "sequence": sequence,
        "deleted_at": None,
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
    monkeypatch.setattr(uc, "_load_published_soul_version", lambda _: None)
    monkeypatch.setattr(uc, "_fetch_pending_approvals", lambda _: [])
    monkeypatch.setattr(uc, "_fetch_all_agent_revisions", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(uc, "_request_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected network call")))

    rc = uc.cmd_reconcile(argparse.Namespace(agent_id="larry", dry_run=True))
    stdout = capsys.readouterr().out.splitlines()

    assert rc == 0
    assert order[0] == "print"
    assert stdout[0] == "target api_url=http://localhost:8010 tenant_id=tenant-dev agent_id=larry"
