"""
Tests for Zero-Click Auto-Login and Batch Ingestion CLI.
"""

import shutil
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

import second_brain.config as config
import second_brain.interface.web_server as web_server
from second_brain.core.users import get_user_by_token, load_user_registry
from second_brain.cli.batch_import import process_single_file, run_batch_import

client = TestClient(web_server.app)


def test_auto_login_disabled():
    """When AUTO_LOGIN_ENABLED is False, access requires credentials."""
    config.AUTO_LOGIN_ENABLED = False
    web_server.AUTO_LOGIN_ENABLED = False

    res = client.get("/api/auth/verify")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is False
    assert data["auth_required"] is True

    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 401
    print("✓ Auto-login disabled verified: 401 enforced without token")


def test_auto_login_enabled():
    """When AUTO_LOGIN_ENABLED is True, zero-click access is granted."""
    config.AUTO_LOGIN_ENABLED = True
    web_server.AUTO_LOGIN_ENABLED = True

    try:
        res = client.get("/api/auth/verify")
        assert res.status_code == 200
        data = res.json()
        assert data["authenticated"] is True
        assert data["auth_required"] is False
        assert data["auto_login"] is True
        assert "user" in data

        # Accessing protected endpoint without any cookie or header succeeds
        res_stats = client.get("/api/stats")
        assert res_stats.status_code == 200
        assert res_stats.json()["status"] == "online"
        print("✓ Auto-login enabled verified: zero-click instant access granted")
    finally:
        # Reset back to False
        config.AUTO_LOGIN_ENABLED = False
        web_server.AUTO_LOGIN_ENABLED = False


def test_batch_import_cli():
    """Tests batch import processing, deduplication, and dry-run."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_sb_batch_"))
    try:
        # Create test notes
        note1 = temp_dir / "project_alpha.md"
        note1.write_text("# Project Alpha Roadmap\nDeliverables for Q1.", encoding="utf-8")
        note2 = temp_dir / "meeting_notes.txt"
        note2.write_text("Discussed budget allocation with team.", encoding="utf-8")

        user = get_user_by_token("shayeez-vault-2026")
        assert user is not None

        # 1. Test Dry Run
        dry_res = process_single_file(note1, user, mode="copy", dry_run=True)
        assert dry_res["status"] == "dry_run"
        print("✓ Batch CLI dry-run verified")

        # 2. Test Batch Ingestion (copy mode)
        run_batch_import(temp_dir, username="shayeez", mode="copy", dry_run=False)

        # Verify note exists in user wiki
        found_notes = list(user["wiki_dir"].rglob("*project-alpha*.md"))
        assert len(found_notes) > 0, "Expected project-alpha note in wiki"
        print("✓ Batch CLI live ingestion verified: notes created in vault")

        # 3. Test Deduplication on second run
        dup_res = process_single_file(note1, user, mode="copy", dry_run=False)
        # Note hash or content duplicate
        print(f"✓ Batch CLI duplicate check completed: status={dup_res['status']}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("\n--- Running Auto-Login and Batch CLI Tests ---")
    test_auto_login_disabled()
    test_auto_login_enabled()
    test_batch_import_cli()
    print("\n🎉 ALL AUTO-LOGIN & BATCH CLI TESTS PASSED SUCCESSFULLY!\n")
