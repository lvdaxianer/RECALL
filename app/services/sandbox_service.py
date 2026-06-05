"""
Sandbox/Profile 隔离服务

第一阶段只生成隔离 profile，不启动容器或进程。

@author lvdaxianerplus
@date 2026-06-02
"""

from pathlib import Path
from typing import Optional

from app.models.agent_schemas import SandboxProfile

PROFILE_DIRECTORY_MODE = 0o700


class SandboxService:
    """构建用户或 session 隔离 profile。"""

    def __init__(self, base_dir: str = "var/agent_profiles"):
        self.base_dir = Path(base_dir)

    def build_profile(self, user_id: str, session_id: Optional[str], runtime: str = "local") -> SandboxProfile:
        """根据用户和会话生成运行隔离 profile。"""
        scope = session_id or "user"
        root = self.base_dir / user_id / scope
        runtime_id = f"{runtime}:{user_id}:{scope}"
        return SandboxProfile(
            user_id=user_id,
            session_id=session_id,
            runtime_id=runtime_id,
            namespace=f"rag-agent:{user_id}:{scope}",
            memory_path=str(root / "memory"),
            config_path=str(root / "config"),
            cache_namespace=f"{user_id}:{scope}",
        )

    def ensure_profile_directories(self, profile: SandboxProfile) -> SandboxProfile:
        """创建 profile 目录并限制为当前用户可访问。"""
        for path in [profile.memory_path, profile.config_path]:
            directory = Path(path)
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(PROFILE_DIRECTORY_MODE)
        return profile


_sandbox_service: Optional[SandboxService] = None


def get_sandbox_service() -> SandboxService:
    """获取全局 SandboxService 实例。"""
    global _sandbox_service
    if _sandbox_service is None:
        _sandbox_service = SandboxService()
    else:
        pass
    return _sandbox_service
