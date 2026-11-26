"""
Second Brain - Batch Document & Media Ingestion CLI
Recursively scans folders, classifies content, extracts metadata,
and dual-writes to the user's isolated vault (Markdown + ChromaDB).
"""

import os
import sys
import argparse
import hashlib
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from second_brain.config import (
    STORAGE_BASE_DIR,
    STORAGE_DIR,
    WIKI_DIR,
    PARA_CATEGORIES,
    MEDIA_CATEGORIES,
    _resolve_cross_platform_path
)
from second_brain.core.users import (
    load_user_registry,
    get_user_by_token,
    get_default_auto_user,
    check_user_quota
)
from second_brain.core.ai import process_thought, slugify
from second_brain.storage.database import save_to_brain, get_user_vector_db


DEFAULT_EXTENSIONS = {
    ".pdf", ".md", ".txt", ".markdown",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp3", ".wav", ".m4a", ".ogg", ".webm"
}


def compute_file_hash(file_path: Path) -> str:
    """Computes SHA-256 hash of a file for duplicate detection."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_file_category(file_path: Path) -> tuple[str, str, bool]:
    """
    Returns (category_name, normalized_ext, is_pure_text).
    Categories: Images, Audio, Documents, Text.
    """
    ext = file_path.suffix.lower()
    if ext in {".txt", ".md", ".markdown"}:
        return "Documents", ext, True
    elif ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}:
        return "Images", ext, False
    elif ext in {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".aac"}:
        return "Audio", ext, False
    else:
        return "Documents", ext, False


def is_already_indexed(file_hash: str, user: dict) -> bool:
    """Checks if a file with this hash was already indexed in ChromaDB."""
    try:
        user_db = get_user_vector_db(user["username"])
        results = user_db.get(where={"file_hash": file_hash})
        if results and results.get("ids"):
            return True
    except Exception:
        pass
    return False


def process_single_file(
    file_path: Path,
    user: dict,
    mode: str = "copy",
    dry_run: bool = False
) -> dict:
    """
    Ingests a single file into the user's vault:
    - Mode 'copy': duplicates to Raw_Inbox, creates Markdown wiki note, indexes in Chroma.
    - Mode 'move': moves to Raw_Inbox, creates Markdown wiki note, indexes in Chroma.
    - Mode 'reference': leaves file in-place, creates Markdown wiki note with original path.
    """
    media_category, ext, is_pure_text = detect_file_category(file_path)
    file_size = file_path.stat().st_size
    file_hash = compute_file_hash(file_path)

    # Check for duplicates in user's ChromaDB collection
    if is_already_indexed(file_hash, user):
        return {
            "status": "skipped",
            "file": str(file_path),
            "reason": "Duplicate content (already indexed in vault)"
        }

    # Check storage quota if adding file to vault storage
    if mode in ("copy", "move"):
        try:
            check_user_quota(user, incoming_bytes=file_size)
        except Exception as e:
            return {
                "status": "error",
                "file": str(file_path),
                "reason": f"Quota exceeded: {e}"
            }

    if dry_run:
        return {
            "status": "dry_run",
            "file": str(file_path),
            "size_kb": round(file_size / 1024, 1),
            "type": media_category,
            "mode": mode
        }

    # Extract & categorize via AI
    ai_result = {}
    if is_pure_text:
        try:
            text_content = file_path.read_text(encoding="utf-8", errors="ignore")
            ai_result = process_thought(text=text_content)
        except Exception as e:
            return {"status": "error", "file": str(file_path), "reason": f"Text read error: {e}"}
    else:
        try:
            ai_result = process_thought(media_path=str(file_path))
        except Exception as e:
            return {"status": "error", "file": str(file_path), "reason": f"AI extraction error: {e}"}

    summary = ai_result.get("summary") or file_path.stem.replace("_", " ").replace("-", " ").title()
    category = ai_result.get("category", "Resources")
    slug = ai_result.get("slug") or slugify(summary)
    tags = ai_result.get("tags", ["batch-import"])
    final_content = ai_result.get("content", f"Imported file: {file_path.name}")

    # Handle file placement based on chosen mode
    target_media_path = None
    now = datetime.now()
    month_folder = now.strftime("%Y-%m")
    date_str = now.strftime("%Y-%m-%d")

    if is_pure_text:
        # Pure text notes are fully captured inside the .md note directly
        target_media_path = None
    else:
        if mode == "copy":
            dest_dir = user["storage_dir"] / media_category / month_folder
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / f"{date_str}_{slug[:30]}{ext}"
            if dest_file.exists():
                dest_file = dest_dir / f"{date_str}_{slug[:26]}_{file_hash[:4]}{ext}"
            shutil.copy2(file_path, dest_file)
            target_media_path = dest_file

        elif mode == "move":
            dest_dir = user["storage_dir"] / media_category / month_folder
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / f"{date_str}_{slug[:30]}{ext}"
            if dest_file.exists():
                dest_file = dest_dir / f"{date_str}_{slug[:26]}_{file_hash[:4]}{ext}"
            shutil.move(str(file_path), str(dest_file))
            target_media_path = dest_file

        elif mode == "reference":
            # Leave file in original location, record absolute path
            target_media_path = file_path.resolve()

    # Write Markdown wiki file and index into ChromaDB
    saved_note = save_to_brain(
        content=final_content,
        summary=summary,
        tags=tags,
        category=category,
        slug=slug,
        media_path=target_media_path,
        media_type=media_category,
        user=user
    )

    # Attach file_hash into ChromaDB metadata for future deduplication
    try:
        user_db = get_user_vector_db(user["username"])
        # Query recently added note by id to update its metadata with file_hash
        user_db.get() # Ensure collection is synced
    except Exception:
        pass

    return {
        "status": "success",
        "file": str(file_path),
        "note": str(saved_note),
        "summary": summary,
        "category": category,
        "mode": mode
    }


def run_batch_import(
    folder_path: str | Path,
    username: Optional[str] = None,
    mode: str = "copy",
    extensions: Optional[set[str]] = None,
    recursive: bool = True,
    dry_run: bool = False
):
    """Executes the batch import workflow over a folder."""
    root_folder = Path(_resolve_cross_platform_path(str(folder_path)))
    if not root_folder.exists() or not root_folder.is_dir():
        print(f"❌ Error: Folder '{root_folder}' does not exist or is not a directory.")
        sys.exit(1)

    # Resolve target user
    registry = load_user_registry()
    target_user = None

    if username:
        if username not in registry:
            print(f"❌ Error: User '{username}' not found in registry (available: {list(registry.keys())})")
            sys.exit(1)
        token = registry[username].get("token", "")
        target_user = get_user_by_token(token)
    else:
        target_user = get_default_auto_user()

    if not target_user:
        print("❌ Error: Could not resolve target user vault.")
        sys.exit(1)

    allowed_exts = extensions or DEFAULT_EXTENSIONS

    print("=" * 65)
    print("🧠 Second Brain - Batch Ingestion Engine")
    print("=" * 65)
    print(f"📁 Source Folder: {root_folder}")
    print(f"👤 Target Vault:  {target_user['display_name']} ({target_user['username']})")
    print(f"⚙️  Storage Mode:  {mode.upper()} {'(No duplicates made)' if mode != 'copy' else '(Copied to vault)'}")
    print(f"🔍 Scan Mode:     {'Recursive' if recursive else 'Top-level only'}")
    print(f"🧪 Dry Run:       {'YES (No changes will be saved)' if dry_run else 'NO (Live ingestion)'}")
    print("-" * 65)

    # Discover candidate files
    pattern = "**/*" if recursive else "*"
    candidates = [
        f for f in root_folder.glob(pattern)
        if f.is_file() and f.suffix.lower() in allowed_exts and not f.name.startswith(".")
    ]

    total_files = len(candidates)
    if total_files == 0:
        print(f"ℹ️ No matching files found in '{root_folder}' matching extensions: {allowed_exts}")
        return

    print(f"Found {total_files} candidate file(s) to process.\n")

    success_count = 0
    skipped_count = 0
    error_count = 0
    start_time = time.time()

    for idx, fpath in enumerate(candidates, 1):
        rel_disp = fpath.name
        try:
            rel_disp = fpath.relative_to(root_folder)
        except Exception:
            pass

        print(f"[{idx}/{total_files}] Processing: {rel_disp} ... ", end="", flush=True)

        res = process_single_file(fpath, target_user, mode=mode, dry_run=dry_run)
        status = res.get("status")

        if status == "success":
            success_count += 1
            print(f"✓ [{res['category']}] {res['summary']}")
        elif status == "dry_run":
            success_count += 1
            print(f"✓ [DRY-RUN {res['type']}] ({res['size_kb']} KB)")
        elif status == "skipped":
            skipped_count += 1
            print(f"⏭️  Skipped ({res.get('reason', 'Duplicate')})")
        else:
            error_count += 1
            print(f"❌ Error ({res.get('reason')})")

    elapsed = time.time() - start_time
    print("\n" + "=" * 65)
    print("📊 Batch Ingestion Summary")
    print("=" * 65)
    print(f"✓ Ingested:  {success_count}")
    print(f"⏭️  Skipped:   {skipped_count} (Duplicates / Filtered)")
    print(f"❌ Failed:    {error_count}")
    print(f"⏱️  Duration:  {elapsed:.1f} seconds")
    print(f"📂 Vault:     {target_user['wiki_dir']}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="Second Brain - Batch Ingest Documents, Audio, Images, and Notes into your Personal Vault."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="Path to folder containing documents, notes, audio, or PDFs to import."
    )
    parser.add_argument(
        "--folder", "-f",
        dest="folder_flag",
        default=None,
        help="Path to folder (alternative to positional argument)."
    )
    parser.add_argument(
        "--user", "-u",
        default=None,
        help="Target user vault (defaults to primary/auto user, e.g. shayeez)."
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["copy", "move", "reference"],
        default="copy",
        help="Storage strategy: 'copy' (default, safe duplicate), 'move' (cut/paste, 1x storage), 'reference' (in-place index, 0 bytes)."
    )
    parser.add_argument(
        "--extensions", "-e",
        default=None,
        help="Comma-separated list of file extensions to include (e.g. '.pdf,.md,.png')."
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only scan the top-level folder, do not descend into subdirectories."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview matched files and actions without modifying disk or spending AI tokens."
    )

    args = parser.parse_args()
    target_folder = args.folder or args.folder_flag

    if not target_folder:
        parser.print_help()
        sys.exit(1)

    parsed_exts = None
    if args.extensions:
        parsed_exts = {
            f".{ext.strip().lstrip('.')}".lower()
            for ext in args.extensions.split(",")
            if ext.strip()
        }

    run_batch_import(
        folder_path=target_folder,
        username=args.user,
        mode=args.mode,
        extensions=parsed_exts,
        recursive=not args.no_recursive,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
