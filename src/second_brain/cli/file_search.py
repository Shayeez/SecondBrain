"""
Second Brain - Cross-Platform Local Machine File Search & Indexing CLI.
Provides 'brain-scan' (to index local directories) and 'brain-find' (to search files & inspect content).
"""

import sys
import argparse
import time
from pathlib import Path

from second_brain.config import LOCAL_SEARCH_DIRS, LOCAL_INDEX_DB_PATH
from second_brain.core.local_search import (
    scan_directory,
    scan_all_configured_dirs,
    search_local_files,
    inspect_and_answer_local
)


def run_scan_cli():
    """CLI entry point for scanning / indexing local directories into SQLite FTS5."""
    parser = argparse.ArgumentParser(
        description="Second Brain - Cross-Platform Local Machine File Indexer."
    )
    parser.add_argument(
        "directories",
        nargs="*",
        help="Optional directories to scan (defaults to LOCAL_SEARCH_DIRS from config/env)."
    )
    parser.add_argument(
        "--db",
        default=str(LOCAL_INDEX_DB_PATH),
        help="Path to SQLite FTS5 index database."
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=8,
        help="Maximum directory traversal depth (default: 8)."
    )

    args = parser.parse_args()

    dirs_to_scan = [Path(d).resolve() for d in args.directories] if args.directories else LOCAL_SEARCH_DIRS

    print("=" * 65)
    print("🔍 Second Brain - Local Machine File Indexer (FTS5)")
    print("=" * 65)
    print(f"📦 Database: {args.db}")
    print(f"📁 Targets:  {', '.join(str(d) for d in dirs_to_scan)}")
    print("-" * 65)

    start_time = time.time()
    summary = scan_all_configured_dirs(directories=dirs_to_scan, db_path=Path(args.db))
    elapsed = time.time() - start_time

    print("\n" + "=" * 65)
    print("📊 Scan Summary")
    print("=" * 65)
    print(f"✓ Total Files Scanned:  {summary['scanned']}")
    print(f"➕ Newly Indexed:        {summary['inserted']}")
    print(f"🔄 Updated (Modified):   {summary['updated']}")
    print(f"🗑️  Pruned (Deleted):     {summary['deleted']}")
    print(f"⚠️  Access Errors:        {summary['errors']}")
    print(f"⏱️  Duration:             {elapsed:.2f} seconds")
    print("=" * 65)


def run_find_cli():
    """CLI entry point for searching files or inspecting contents on-demand."""
    parser = argparse.ArgumentParser(
        description="Second Brain - Fast Local Machine File Search & On-Demand AI Inspection."
    )
    parser.add_argument(
        "query",
        help="Search query or question (e.g. 'invoice 2026', 'contract payment terms', 'budget presentation')."
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=10,
        help="Maximum number of files to return (default: 10)."
    )
    parser.add_argument(
        "--ext", "-e",
        default=None,
        help="Filter by file extension (e.g. '.pdf', '.docx', '.png')."
    )
    parser.add_argument(
        "--inspect", "-i",
        action="store_true",
        help="Tier 2 On-Demand Inspection: Open matching candidate files and use AI to answer question."
    )

    args = parser.parse_args()

    if args.inspect:
        print(f"🧠 Inspecting local files for: '{args.query}' ...\n")
        res = inspect_and_answer_local(args.query, max_files=3)
        print("💡 Answer:\n" + res["answer"] + "\n")
        if res.get("sources"):
            print("📄 Source Files Inspected:")
            for s in res["sources"]:
                print(f"   • {s['filename']} ({s['filepath']})")
    else:
        results = search_local_files(args.query, limit=args.limit, extension=args.ext)
        print("=" * 65)
        print(f"🔍 Local Search Results for: '{args.query}' ({len(results)} found)")
        print("=" * 65)
        if not results:
            print("No matching files found. Have you run 'brain-scan' to index your folders?")
            return

        for idx, item in enumerate(results, 1):
            print(f"[{idx}] {item['filename']} ({item['size_human']} • {item['modified_at']})")
            print(f"    Path: {item['filepath']}\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        sys.argv.pop(1)
        run_scan_cli()
    else:
        run_find_cli()
