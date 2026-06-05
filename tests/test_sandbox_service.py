from app.services.sandbox_service import SandboxService


def test_build_profile_uses_user_and_session_namespace():
    service = SandboxService(base_dir="var/agent_profiles")

    profile = service.build_profile(user_id="u001", session_id="sess_001", runtime="local")

    assert profile.runtime_id == "local:u001:sess_001"
    assert profile.namespace == "rag-agent:u001:sess_001"
    assert profile.cache_namespace == "u001:sess_001"
    assert profile.memory_path.endswith("var/agent_profiles/u001/sess_001/memory")
    assert profile.config_path.endswith("var/agent_profiles/u001/sess_001/config")


def test_build_profile_without_session_uses_user_scope():
    service = SandboxService(base_dir="var/agent_profiles")

    profile = service.build_profile(user_id="u001", session_id=None, runtime="local")

    assert profile.runtime_id == "local:u001:user"
    assert profile.cache_namespace == "u001:user"


def test_ensure_profile_directories_creates_memory_and_config_paths(tmp_path):
    service = SandboxService(base_dir=str(tmp_path))
    profile = service.build_profile(user_id="u001", session_id="sess_001", runtime="local")

    ensured = service.ensure_profile_directories(profile)

    assert ensured == profile
    assert (tmp_path / "u001" / "sess_001" / "memory").is_dir()
    assert (tmp_path / "u001" / "sess_001" / "config").is_dir()
