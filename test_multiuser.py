import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from second_brain.interface.web_server import app, FAILED_LOGIN_ATTEMPTS
from second_brain.core.users import load_user_registry, get_user_by_token

client = TestClient(app)

def run_multiuser_tests():
    print("\n--- Starting Multi-User Tenant Isolation Tests ---")
    FAILED_LOGIN_ATTEMPTS.clear()

    # 1. Verify User Registry
    users = load_user_registry()
    assert "shayeez" in users
    assert "shamim" in users
    assert "shayeez_shamim" in users
    print("✓ User registry loaded with users: 'shayeez', 'shamim', 'shayeez_shamim'")

    # Verify maximum storage quota for shayeez_shamim
    assert users["shayeez_shamim"]["max_storage_mb"] == 51200
    assert users["shayeez_shamim"]["max_storage_mb"] > users["shayeez"]["max_storage_mb"]
    print(f"✓ Maximum storage quota verified for 'shayeez_shamim': {users['shayeez_shamim']['max_storage_mb']} MB (50 GB)")

    # 2. Login as Shayeez
    res1 = client.post("/api/auth/login", json={"token": "shayeez-vault-2026"})
    assert res1.status_code == 200, f"Failed login: {res1.text}"
    cookie_shayeez = res1.cookies
    assert res1.json()["user"]["username"] == "shayeez"
    print("✓ Successfully authenticated user 'shayeez'")

    # Capture a note for Shayeez
    cap1 = client.post(
        "/api/capture",
        data={"text": "Project Phoenix secret roadmap deadline is Dec 2026", "mode": "note"},
        cookies=cookie_shayeez
    )
    assert cap1.status_code == 200, f"Capture failed: {cap1.text}"
    print("✓ Shayeez captured a private note: 'Project Phoenix'")

    # 3. Login as Shamim
    res2 = client.post("/api/auth/login", json={"token": "shamim-vault-2026"})
    assert res2.status_code == 200
    cookie_shamim = res2.cookies
    assert res2.json()["user"]["username"] == "shamim"
    print("✓ Successfully authenticated user 'shamim'")

    # Verify Shamim has 0 notes and cannot see Shayeez's notes
    notes_shamim = client.get("/api/notes", cookies=cookie_shamim).json()
    stats_shamim = client.get("/api/stats", cookies=cookie_shamim).json()
    assert stats_shamim["user"]["username"] == "shamim"
    assert stats_shamim["total_notes"] == 0, f"Shamim leaked notes: {notes_shamim}"
    print("✓ Verified Shamim has 0 notes (Total isolation from Shayeez)")

    # 4. Login as Shayeez_Shamim
    res3 = client.post("/api/auth/login", json={"token": "shayeez-shamim-vault-2026"})
    assert res3.status_code == 200
    cookie_shared = res3.cookies
    assert res3.json()["user"]["username"] == "shayeez_shamim"
    print("✓ Successfully authenticated user 'shayeez_shamim'")

    # 5. Physical Folder Isolation Verification for all 3 users
    u_shayeez = get_user_by_token("shayeez-vault-2026")
    u_shamim = get_user_by_token("shamim-vault-2026")
    u_shared = get_user_by_token("shayeez-shamim-vault-2026")

    assert u_shayeez["user_root"].exists()
    assert u_shamim["user_root"].exists()
    assert u_shared["user_root"].exists()

    # Verify each user has a unique folder
    assert len({u_shayeez["user_root"], u_shamim["user_root"], u_shared["user_root"]}) == 3
    print(f"✓ Physical disk isolation verified:")
    print(f"   • Shayeez Vault:        {u_shayeez['user_root']}")
    print(f"   • Shamim Vault:         {u_shamim['user_root']}")
    print(f"   • Shayeez_Shamim Vault: {u_shared['user_root']}")

    print("\n🎉 ALL MULTI-USER ISOLATION TESTS PASSED WITH 100% SUCCESS!\n")

if __name__ == "__main__":
    run_multiuser_tests()

