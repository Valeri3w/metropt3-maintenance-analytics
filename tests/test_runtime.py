from metropt.runtime import (
    apply_secret_environment,
    demo_mode_from_environment,
    is_demo_mode,
)


def test_apply_secret_environment_sets_only_missing_keys() -> None:
    environ = {"DATABASE_URL": "postgresql://existing"}
    secrets = {
        "DATABASE_URL": "postgresql://secret",
        "METROPT_DEMO_MODE": "true",
    }

    apply_secret_environment(secrets, environ)

    assert environ["DATABASE_URL"] == "postgresql://existing"
    assert environ["METROPT_DEMO_MODE"] == "true"


def test_is_demo_mode_accepts_true_forms() -> None:
    assert is_demo_mode("1") is True
    assert is_demo_mode("true") is True
    assert is_demo_mode("YES") is True
    assert is_demo_mode("false") is False
    assert is_demo_mode(None) is False


def test_demo_mode_from_environment_reads_the_runtime_value(monkeypatch) -> None:
    monkeypatch.setenv("METROPT_DEMO_MODE", "on")

    assert demo_mode_from_environment() is True
