#!/usr/bin/env python3
"""
Second Brain - Vault Cleanup Utility
Cleans up automated test notes and resets ChromaDB collections.
"""

import sys
import argparse
from pathlib import Path
from second_brain.core.users import load_user_registry, get_default_auto_user
from second_brain.storage.database import get_user_vector_db

def clean_user_vault(username: str, dry_run: bool = True, clean_raw: bool = True):
    registry = load_user_registry()
    if username not in registry:
        print(f"❌ User '{username}' not found in registry.")
        return

    from second_brain.core.users import get_user_by_token
    token = registry[username].get("token", "")
    user = get_user_by_token(token)
    if not user:
        print(f"❌ Could not resolve user '{username}'.")
        return

    wiki_dir = user["wiki_dir"]
    storage_dir = user["storage_dir"]

    print(f"\n📁 Vault Wiki Directory: {wiki_dir}")
    md_files = list(wiki_dir.rglob("*.md"))
    print(f"📄 Found {len(md_files)} markdown note(s).")

    print(f"📁 Raw Storage Directory: {storage_dir}")
    raw_files = [f for f in storage_dir.rglob("*") if f.is_file() and f.name.lower() != "desktop.ini"]
    print(f"📦 Found {len(raw_files)} raw inbox file(s).")

    vdb = get_user_vector_db(username)
    col = vdb._collection
    doc_count = col.count()
    print(f"🧠 ChromaDB documents in '{col.name}': {doc_count}")

    if not md_files and not raw_files and doc_count == 0:
        print(f"✓ Vault for '{username}' is already completely clean.")
        return

    if dry_run:
        print("\n🔍 DRY-RUN MODE (No files deleted):")
        for f in md_files:
            print(f"   • [WOULD DELETE NOTE] {f.relative_to(wiki_dir)}")
        if clean_raw:
            for f in raw_files:
                print(f"   • [WOULD DELETE RAW]  {f.relative_to(storage_dir)}")
        print(f"   • [WOULD RESET] ChromaDB collection '{col.name}' ({doc_count} embeddings)")
        print("\n👉 To execute real cleanup, run: python clean_vault.py --confirm")
        return

    # Real execution
    print("\n🗑️  Executing cleanup...")
    deleted_md = 0
    for f in md_files:
        try:
            f.unlink()
            deleted_md += 1
            print(f"   ✓ Deleted Note: {f.name}")
        except Exception as e:
            print(f"   ❌ Error deleting {f.name}: {e}")

    deleted_raw = 0
    if clean_raw:
        for f in raw_files:
            try:
                f.unlink()
                deleted_raw += 1
                print(f"   ✓ Deleted Raw File: {f.name}")
            except Exception as e:
                print(f"   ❌ Error deleting raw file {f.name}: {e}")

    # Clean empty directories in Raw_Inbox
    try:
        for p in sorted(storage_dir.rglob("*"), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    except Exception:
        pass

    # Reset ChromaDB
    try:
        all_ids = col.get()["ids"]
        if all_ids:
            col.delete(ids=all_ids)
            print(f"   ✓ Reset ChromaDB collection '{col.name}' (removed {len(all_ids)} entries).")
    except Exception as e:
        print(f"   ⚠️ Could not reset ChromaDB collection: {e}")

    print(f"\n🎉 Vault for '{username}' is now completely clean and empty!")
    print(f"   Deleted {deleted_md} note(s), {deleted_raw} raw file(s), and purged {doc_count} vector embedding(s).")

def main():
    parser = argparse.ArgumentParser(description="Clean up test notes from user vault.")
    parser.add_argument("--user", default=None, help="Specific username to clean (default: active auto-login user)")
    parser.add_argument("--confirm", action="store_true", help="Confirm deletion (without this, runs in dry-run mode)")
    parser.add_argument("--keep-raw", action="store_true", help="Keep raw media files in Raw_Inbox (default: clean all)")
    args = parser.parse_args()

    target_user = args.user
    if not target_user:
        auto_user = get_default_auto_user()
        target_user = auto_user["username"] if auto_user else "shayeez"

    clean_user_vault(target_user, dry_run=not args.confirm, clean_raw=not args.keep_raw)

if __name__ == "__main__":
    main()
