"""
Runtime Sandbox 编排服务

第一版提供 local/noop runtime 管理，负责目录权限、状态和环境变量白名单。

@author lvdaxianerplus
@date 2026-06-03
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.agent_schemas import SandboxProfile

DIRECTORY_PRIVATE_MODE = 0o700
DEFAULT_IDLE_TIMEOUT_SECONDS = 1800
RUNTIME_STATUS_RUNNING = "running"
RUNTIME_STATUS_STOPPED = "stopped"
RUNTIME_STATUS_NOT_FOUND = "not_found"
RUNTIME_ENV_ALLOWLIST = {
    "AGENT_RUNTIME_MODE",
    "AGENT_RUNTIME_BASE_URL",
    "AGENT_RUNTIME_API_KEY",
    "MODEL_NAME",
    "MODEL_API_KEY",
    "MODEL_REQUEST_URL",
    "RAG_STATE_DB_PATH",
}
SENSITIVE_ENV_SUFFIXES = ("KEY", "TOKEN", "SECRET", "PASSWORD")
REDACTED_VALUE = "[REDACTED]"


@dataclass
class RuntimeState:
    """本地 runtime 状态。"""

    runtime_id: str
    namespace: str
    status: str
    memory_path: str
    config_path: str
    created_at: str
    last_seen_at: str


class LocalRuntimeOrchestrator:
    """local/noop Runtime 编排器。"""

    def __init__(self, idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS):
        self.idle_timeout_seconds = idle_timeout_seconds
        self._runtimes: dict[str, RuntimeState] = {}

    def ensure_runtime(self, profile: SandboxProfile) -> RuntimeState:
        """确保 runtime profile 目录存在并登记运行状态。"""
        _ensure_private_directory(profile.memory_path)
        _ensure_private_directory(profile.config_path)
        now = _now_iso()
        runtime = self._runtimes.get(profile.runtime_id)
        if runtime is None:
            runtime = RuntimeState(
                runtime_id=profile.runtime_id,
                namespace=profile.namespace,
                status=RUNTIME_STATUS_RUNNING,
                memory_path=profile.memory_path,
                config_path=profile.config_path,
                created_at=now,
                last_seen_at=now,
            )
        else:
            runtime.status = RUNTIME_STATUS_RUNNING
            runtime.last_seen_at = now
        self._runtimes[profile.runtime_id] = runtime
        return runtime

    def health_check(self, runtime_id: str) -> dict:
        """检查 runtime 状态。"""
        runtime = self._runtimes.get(runtime_id)
        if runtime is None:
            return {"runtime_id": runtime_id, "status": RUNTIME_STATUS_NOT_FOUND}
        else:
            return {
                "runtime_id": runtime_id,
                "status": runtime.status,
                "last_seen_at": runtime.last_seen_at,
            }

    def stop_runtime(self, runtime_id: str) -> dict:
        """停止 runtime。"""
        runtime = self._runtimes.get(runtime_id)
        if runtime is None:
            return {"runtime_id": runtime_id, "status": RUNTIME_STATUS_NOT_FOUND}
        else:
            runtime.status = RUNTIME_STATUS_STOPPED
            runtime.last_seen_at = _now_iso()
            return {"runtime_id": runtime_id, "status": runtime.status}

    def cleanup_idle_runtimes(self) -> dict:
        """停止超过 idle timeout 的 running runtime。"""
        stopped_count = 0
        now = datetime.now(timezone.utc)
        for runtime in self._runtimes.values():
            if self._should_stop_idle_runtime(runtime, now):
                runtime.status = RUNTIME_STATUS_STOPPED
                runtime.last_seen_at = _now_iso()
                stopped_count += 1
            else:
                pass
        return {"stopped_count": stopped_count}

    def _should_stop_idle_runtime(self, runtime: RuntimeState, now: datetime) -> bool:
        """判断 runtime 是否空闲超时。"""
        if runtime.status != RUNTIME_STATUS_RUNNING:
            return False
        else:
            pass
        last_seen = datetime.fromisoformat(runtime.last_seen_at)
        return (now - last_seen).total_seconds() > self.idle_timeout_seconds


def filter_runtime_env(env: Optional[dict[str, str]] = None) -> dict[str, str]:
    """按白名单过滤 runtime 环境变量。"""
    source = env if env is not None else os.environ
    return {
        key: source[key]
        for key in RUNTIME_ENV_ALLOWLIST
        if key in source
    }


def summarize_runtime_env(env: dict[str, str]) -> dict[str, str]:
    """输出脱敏后的 runtime 环境变量摘要。"""
    return {
        key: _redact_env_value(key, value)
        for key, value in env.items()
    }


def _ensure_private_directory(path: str) -> None:
    """创建仅当前用户可读写执行的目录。"""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(DIRECTORY_PRIVATE_MODE)


def _redact_env_value(key: str, value: str) -> str:
    """根据变量名判断是否脱敏。"""
    if key.upper().endswith(SENSITIVE_ENV_SUFFIXES):
        return REDACTED_VALUE
    else:
        return value


def _now_iso() -> str:
    """生成 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


_runtime_orchestrator: Optional[LocalRuntimeOrchestrator] = None


def get_runtime_orchestrator() -> LocalRuntimeOrchestrator:
    """获取全局 runtime orchestrator。"""
    global _runtime_orchestrator
    if _runtime_orchestrator is None:
        _runtime_orchestrator = LocalRuntimeOrchestrator()
    else:
        pass
    return _runtime_orchestrator
