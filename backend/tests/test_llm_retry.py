from app.llm_retry import call_with_llm_retries


def test_call_with_llm_retries_succeeds_after_two_failures():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TimeoutError("temporary timeout")
        return "ok"

    result = call_with_llm_retries(flaky, retries=2)

    assert result == "ok"
    assert attempts["count"] == 3


def test_call_with_llm_retries_raises_after_retry_budget_exhausted():
    attempts = {"count": 0}

    def always_fail():
        attempts["count"] += 1
        raise TimeoutError("still failing")

    try:
        call_with_llm_retries(always_fail, retries=2)
    except TimeoutError as exc:
        assert str(exc) == "still failing"
    else:
        raise AssertionError("expected TimeoutError")

    assert attempts["count"] == 3
