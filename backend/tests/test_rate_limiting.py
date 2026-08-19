"""/auth/login rate limiting (5/minute per client IP)."""


def test_sixth_rapid_login_is_rate_limited(client):
    responses = [
        client.post(
            "/auth/login", json={"username": "nobody", "password": "wrong"}
        )
        for _ in range(6)
    ]
    # First five attempts are evaluated normally (bad credentials -> 401)...
    assert all(r.status_code == 401 for r in responses[:5])
    # ...the sixth hits the limiter with a clean JSON payload, not HTML.
    sixth = responses[5]
    assert sixth.status_code == 429
    body = sixth.json()
    assert body["error"] == "rate_limit_exceeded"
    assert "5 per 1 minute" in body["detail"]
