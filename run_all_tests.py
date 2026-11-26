#!/usr/bin/env python3
"""
Second Brain - Unified Test Suite Runner
Runs all automated unit, integration, multi-user, and local search test suites.
"""

import sys
import os
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

TEST_SUITES = [
    {
        "name": "Authentication & Session Security",
        "file": "test_auth.py",
        "description": "Token auth, cookies, bearer headers, rate limiting, and PWA assets."
    },
    {
        "name": "Zero-Click Auto-Login & Batch CLI",
        "file": "test_autologin_and_batch.py",
        "description": "Auto-login toggle, batch ingestion CLI, dry-runs, and SHA-256 deduplication."
    },
    {
        "name": "Local Machine File Search (Tier 1 & Tier 2)",
        "file": "test_local_search.py",
        "description": "SQLite FTS5 indexing, BM25 matching, pruning, and Tier 2 live AI inspection."
    },
    {
        "name": "Multi-User Isolation & Tenant Quotas",
        "file": "test_multiuser.py",
        "description": "Tenant folder isolation, quota enforcement, ChromaDB separation, and private query barriers."
    }
]

def run_suite(suite_info):
    test_file = REPO_ROOT / suite_info["file"]
    if not test_file.exists():
        return False, 0.0, f"File {suite_info['file']} not found"

    print("\n" + "=" * 70)
    print(f"▶ RUNNING: {suite_info['name']} ({suite_info['file']})")
    print(f"  Purpose: {suite_info['description']}")
    print("=" * 70)

    start_time = time.time()
    try:
        # Run test script using current python interpreter
        result = subprocess.run(
            [sys.executable, str(test_file)],
            cwd=str(REPO_ROOT),
            capture_output=False,
            text=True
        )
        duration = time.time() - start_time
        passed = (result.returncode == 0)
        return passed, duration, ""
    except Exception as e:
        duration = time.time() - start_time
        return False, duration, str(e)

def main():
    print("🧠 Second Brain - Comprehensive Test Suite Runner")
    print(f"Python: {sys.executable}")
    print(f"Root:   {REPO_ROOT}")
    print(f"Suites: {len(TEST_SUITES)}")

    total_start = time.time()
    results = []

    for suite in TEST_SUITES:
        passed, duration, err = run_suite(suite)
        results.append({
            "name": suite["name"],
            "file": suite["file"],
            "passed": passed,
            "duration": duration,
            "error": err
        })

    total_duration = time.time() - total_start

    print("\n" + "=" * 70)
    print("📊 TEST EXECUTION SUMMARY SCORECARD")
    print("=" * 70)
    print(f"{'Test Suite':<44} | {'Status':<10} | {'Duration'}")
    print("-" * 70)

    all_passed = True
    for r in results:
        status_str = "✅ PASS" if r["passed"] else "❌ FAIL"
        if not r["passed"]:
            all_passed = False
        print(f"{r['name']:<44} | {status_str:<10} | {r['duration']:>5.2f}s")

    print("-" * 70)
    print(f"Total Time: {total_duration:.2f}s")

    if all_passed:
        print("\n🎉 ALL TEST SUITES PASSED! Second Brain is verified and production-ready.")
        sys.exit(0)
    else:
        print("\n⚠️ SOME TEST SUITES FAILED. Check the logs above for stack traces.")
        sys.exit(1)

if __name__ == "__main__":
    main()
