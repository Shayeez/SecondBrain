from fastapi.testclient import TestClient
from second_brain.interface.web_server import app, FAILED_LOGIN_ATTEMPTS
from second_brain.config import BRAIN_AUTH_TOKEN

client = TestClient(app)

def test_unauthorized_access():
    """Unauthenticated requests must be rejected with 401."""
    res = client.get("/api/stats")
    assert res.status_code == 401
    assert "Unauthorized" in res.json().get("detail", "")

def test_login_invalid_token():
    """Invalid token should return 401."""
    res = client.post("/api/auth/login", json={"token": "wrong-secret-token"})
    assert res.status_code == 401

def test_login_valid_token_and_cookie():
    """Valid token should return 200, set session cookie, and allow subsequent requests."""
    FAILED_LOGIN_ATTEMPTS.clear()
    res = client.post("/api/auth/login", json={"token": BRAIN_AUTH_TOKEN})
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert "brain_session_token" in res.cookies

    # Now make request using the cookie returned by login
    stats_res = client.get("/api/stats", cookies=res.cookies)
    assert stats_res.status_code == 200
    assert "total_notes" in stats_res.json()

def test_auth_via_bearer_header():
    """Bearer token header should authenticate successfully."""
    headers = {"Authorization": f"Bearer {BRAIN_AUTH_TOKEN}"}
    res = client.get("/api/stats", headers=headers)
    assert res.status_code == 200
    assert "total_notes" in res.json()

def test_auth_via_custom_header():
    """X-Brain-Token header should authenticate successfully."""
    headers = {"X-Brain-Token": BRAIN_AUTH_TOKEN}
    res = client.get("/api/stats", headers=headers)
    assert res.status_code == 200

def test_auth_via_query_param():
    """Query parameter should authenticate successfully."""
    res = client.get(f"/api/stats?token={BRAIN_AUTH_TOKEN}")
    assert res.status_code == 200

def test_pwa_assets():
    """PWA manifest and service worker should be accessible publicly."""
    res_manifest = client.get("/manifest.json")
    assert res_manifest.status_code == 200
    assert "Second Brain" in res_manifest.text

    res_sw = client.get("/sw.js")
    assert res_sw.status_code == 200
    assert "second-brain-v1" in res_sw.text

if __name__ == "__main__":
    test_unauthorized_access()
    print("✓ test_unauthorized_access passed")
    test_login_invalid_token()
    print("✓ test_login_invalid_token passed")
    test_login_valid_token_and_cookie()
    print("✓ test_login_valid_token_and_cookie passed")
    test_auth_via_bearer_header()
    print("✓ test_auth_via_bearer_header passed")
    test_auth_via_custom_header()
    print("✓ test_auth_via_custom_header passed")
    test_auth_via_query_param()
    print("✓ test_auth_via_query_param passed")
    test_pwa_assets()
    print("✓ test_pwa_assets passed")
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")
