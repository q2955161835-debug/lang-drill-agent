import pytest

from langdrill_agent.runtime.retry import RetryPolicy, run_with_retry


def test_retry_succeeds_on_second_attempt() -> None:
    calls = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary")
        return "ok"

    result = run_with_retry(
        operation,
        RetryPolicy(max_attempts=2),
        lambda exc: isinstance(exc, TimeoutError),
        sleep=delays.append,
    )

    assert result == "ok"
    assert calls == 2
    assert delays == [0.25]


def test_retry_stops_for_non_retryable_error() -> None:
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("invalid")

    with pytest.raises(ValueError, match="invalid"):
        run_with_retry(
            operation,
            RetryPolicy(max_attempts=3),
            lambda exc: False,
            sleep=lambda _: None,
        )

    assert calls == 1
