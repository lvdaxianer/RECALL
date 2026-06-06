import os
import stat
from datetime import datetime, timedelta, timezone

from app.services.runtime_orchestrator import LocalRuntimeOrchestrator
from app.services.runtime_orchestrator import filter_runtime_env
from app.services.runtime_orchestrator import summarize_runtime_env
from app.services.sandbox_service import SandboxService


def test_ensure_runtime_creates_profile_directories_with_private_permissions(tmp_path):
    profile = SandboxService(base_dir=str(tmp_path)).build_profile("u001", "sess_001")
    orchestrator = LocalRuntimeOrchestrator()

    runtime = orchestrator.ensure_runtime(profile)

    memory_mode = stat.S_IMODE(os.stat(profile.memory_path).st_mode)
    config_mode = stat.S_IMODE(os.stat(profile.config_path).st_mode)
    assert runtime.runtime_id == profile.runtime_id
    assert runtime.status == "running"
    assert memory_mode == 0o700
    assert config_mode == 0o700


def test_health_check_and_stop_runtime(tmp_path):
    profile = SandboxService(base_dir=str(tmp_path)).build_profile("u001", "sess_001")
    orchestrator = LocalRuntimeOrchestrator()
    orchestrator.ensure_runtime(profile)

    assert orchestrator.health_check(profile.runtime_id)["status"] == "running"

    stopped = orchestrator.stop_runtime(profile.runtime_id)

    assert stopped["status"] == "stopped"
    assert orchestrator.health_check(profile.runtime_id)["status"] == "stopped"


def test_cleanup_idle_runtimes_stops_old_running_runtime(tmp_path):
    profile = SandboxService(base_dir=str(tmp_path)).build_profile("u001", "sess_001")
    orchestrator = LocalRuntimeOrchestrator(idle_timeout_seconds=60)
    orchestrator.ensure_runtime(profile)
    orchestrator._runtimes[profile.runtime_id].last_seen_at = (
        datetime.now(timezone.utc) - timedelta(seconds=120)
    ).isoformat()

    result = orchestrator.cleanup_idle_runtimes()

    assert result["stopped_count"] == 1
    assert orchestrator.health_check(profile.runtime_id)["status"] == "stopped"


def test_filter_runtime_env_uses_allowlist_and_redacts_summary():
    env = filter_runtime_env({
        "AGENT_RUNTIME_MODE": "local",
        "AGENT_RUNTIME_API_KEY": "runtime-secret",
        "MODEL_API_KEY": "secret-model-key",
        "RAG_STATE_DB_PATH": "var/rag_state.sqlite3",
        "UNRELATED_SECRET": "secret",
    })
    summary = summarize_runtime_env(env)

    assert env == {
        "AGENT_RUNTIME_MODE": "local",
        "AGENT_RUNTIME_API_KEY": "runtime-secret",
        "MODEL_API_KEY": "secret-model-key",
        "RAG_STATE_DB_PATH": "var/rag_state.sqlite3",
    }
    assert summary["AGENT_RUNTIME_API_KEY"] == "[REDACTED]"
    assert summary["MODEL_API_KEY"] == "[REDACTED]"
    assert "UNRELATED_SECRET" not in summary
