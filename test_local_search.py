"""
Comprehensive test suite for Cross-Platform Local Machine File Search & Inspection.
Verifies Tier 1 (SQLite FTS5 metadata indexing) and Tier 2 (On-demand AI inspection).
"""

import os
import shutil
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

import second_brain.interface.web_server as web_server
from second_brain.config import BRAIN_AUTH_TOKEN
from second_brain.core.local_search import (
    init_fts_db,
    scan_directory,
    search_local_files,
    inspect_and_answer_local
)

client = TestClient(web_server.app)


def test_fts5_indexing_and_search():
    """Verifies SQLite FTS5 table initialization, crawling, and BM25 search."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_sb_localsearch_"))
    temp_db = temp_dir / "test_index.sqlite3"

    try:
        # Create test folder structure
        folder1 = temp_dir / "Documents" / "Invoices"
        folder1.mkdir(parents=True)
        inv1 = folder1 / "2026_10_Acme_Invoice.pdf"
        inv1.write_text("Dummy PDF content for Acme Corp $1450.00", encoding="utf-8")

        folder2 = temp_dir / "Projects" / "Cloud"
        folder2.mkdir(parents=True)
        proj1 = folder2 / "kubernetes_migration_plan.md"
        proj1.write_text("# Kubernetes Migration Plan\nTimeline and milestones.", encoding="utf-8")

        # 1. Initialize DB and scan
        init_fts_db(temp_db)
        scan_res = scan_directory(temp_dir, db_path=temp_db)
        assert scan_res["inserted"] >= 2, f"Expected at least 2 files indexed, got {scan_res}"
        print(f"✓ Scan directory completed: {scan_res}")

        # 2. Search exact keyword
        results_acme = search_local_files("Acme", db_path=temp_db)
        assert len(results_acme) >= 1
        assert "Acme" in results_acme[0]["filename"]
        print("✓ FTS5 search matched 'Acme' invoice successfully")

        # 3. Search multi-word query
        results_kube = search_local_files("kubernetes migration", db_path=temp_db)
        assert len(results_kube) >= 1
        assert "kubernetes" in results_kube[0]["filename"]
        print("✓ FTS5 search matched multi-word 'kubernetes migration' successfully")

        # 4. Search with extension filter
        results_pdf = search_local_files("Acme", extension=".pdf", db_path=temp_db)
        assert len(results_pdf) == 1
        assert results_pdf[0]["extension"] == ".pdf"
        print("✓ FTS5 search extension filter verified")

        # 5. Incremental update & prune check
        inv1.unlink() # Delete file
        rescan = scan_directory(temp_dir, db_path=temp_db)
        assert rescan["deleted"] >= 1
        assert len(search_local_files("Acme", db_path=temp_db)) == 0
        print("✓ Incremental deletion pruning verified")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_on_demand_inspection():
    """Verifies Tier 2 on-demand inspection reading local files live to answer questions."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_sb_inspect_"))
    try:
        report = temp_dir / "quarterly_budget_summary.txt"
        report.write_text(
            "Acme Corp Financial Summary 2026:\nTotal revenue: $500,000.\nApproved Q4 marketing budget: $45,000.\nStatus: Approved by Shayeez.",
            encoding="utf-8"
        )

        res = inspect_and_answer_local(
            query="What is the approved Q4 marketing budget?",
            candidate_paths=[report]
        )

        assert "sources" in res
        assert len(res["sources"]) == 1
        assert res["files_inspected"] == 1
        assert "45,000" in res["answer"] or "marketing" in res["answer"].lower()
        print(f"✓ Tier 2 on-demand inspection succeeded: {res['answer'][:100]}...")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_web_api_endpoints():
    """Verifies FastAPI endpoints for local search and /find shortcut."""
    # Authenticate
    login_res = client.post("/api/auth/login", json={"token": BRAIN_AUTH_TOKEN})
    assert login_res.status_code == 200
    cookies = login_res.cookies

    # 1. Test /api/local/search
    res_search = client.get("/api/local/search?q=test", cookies=cookies)
    assert res_search.status_code == 200
    assert "files" in res_search.json()
    print("✓ GET /api/local/search endpoint verified")

    # 2. Test /find shortcut in /api/capture
    res_find = client.post(
        "/api/capture",
        data={"text": "/find python", "mode": "auto"},
        cookies=cookies
    )
    assert res_find.status_code == 200
    data = res_find.json()
    assert data["type"] == "find"
    assert "answer" in data
    print("✓ /find command shortcut in /api/capture verified")


if __name__ == "__main__":
    print("\n--- Running Local File Search & Inspection Tests ---")
    test_fts5_indexing_and_search()
    test_on_demand_inspection()
    test_web_api_endpoints()
    print("\n🎉 ALL LOCAL MACHINE FILE SEARCH TESTS PASSED SUCCESSFULLY!\n")
