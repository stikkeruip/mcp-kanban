"""Config resolution tests."""

from tasks_mcp.config import (
    DEFAULT_TRANSITION_POLICY,
    ENV_DB_PATH,
    ENV_TRANSITION_POLICY,
    load_config,
)


def test_env_var_overrides_db_path_and_creates_parent_dir(tmp_path):
    target = tmp_path / "nested" / "dir" / "tasks.db"
    cfg = load_config(env={ENV_DB_PATH: str(target)})
    assert cfg.db_path == target
    assert target.parent.is_dir()


def test_policy_defaults_to_free_and_is_overridable(tmp_path):
    db = str(tmp_path / "t.db")
    assert load_config(env={ENV_DB_PATH: db}).transition_policy == (
        DEFAULT_TRANSITION_POLICY
    )
    cfg = load_config(env={ENV_DB_PATH: db, ENV_TRANSITION_POLICY: "linear"})
    assert cfg.transition_policy == "linear"
