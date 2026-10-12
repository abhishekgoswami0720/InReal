"""Public visitors (through a tunnel or a host) can read but never change data."""
import app as app_mod

TUNNEL = {"Cf-Connecting-Ip": "203.0.113.9", "X-Forwarded-For": "203.0.113.9"}


def client():
    return app_mod.app.test_client()


def test_tunnel_visitor_can_read():
    c = client()
    assert c.get("/api/internships", headers=TUNNEL).status_code == 200
    assert c.get("/api/moderation/status", headers=TUNNEL).status_code == 200
    assert c.get("/api/whoami", headers=TUNNEL).get_json() == {"can_edit": False}


def test_tunnel_visitor_cannot_write():
    c = client()
    for method, url in [("post", "/api/scrape"), ("post", "/api/clear"), ("post", "/api/alerts/dismiss"),
                        ("post", "/api/moderation/verdict"), ("get", "/api/moderation/pending?claim=1"),
                        ("get", "/api/moderation/resolve?id=x"), ("get", "/api/moderation/patterns")]:
        assert getattr(c, method)(url, headers=TUNNEL).status_code == 403, url


def test_admin_token_unlocks(monkeypatch):
    monkeypatch.setenv("INREAL_ADMIN_TOKEN", "s3cret")
    c = client()
    assert c.post("/api/moderation/verdict", json={}, headers={**TUNNEL, "X-InReal-Token": "wrong"}).status_code == 403
    assert c.post("/api/moderation/verdict", json={}, headers={**TUNNEL, "X-InReal-Token": "s3cret"}).status_code != 403


def test_empty_token_never_matches(monkeypatch):
    monkeypatch.delenv("INREAL_ADMIN_TOKEN", raising=False)
    r = client().post("/api/clear", headers={**TUNNEL, "X-InReal-Token": ""})
    assert r.status_code == 403


def test_laptop_itself_can_write():
    c = client()
    assert c.get("/api/whoami").get_json() == {"can_edit": True}
    assert c.post("/api/moderation/verdict", json={"id": "nope", "status": "approved"}).status_code != 403
