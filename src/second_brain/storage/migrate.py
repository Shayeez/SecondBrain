import os
import re
import shutil
import logging
from pathlib import Path
from datetime import datetime
from second_brain.config import STORAGE_DIR, WIKI_DIR, PARA_CATEGORIES, MEDIA_CATEGORIES
from second_brain.core.ai import slugify, process_thought
from second_brain.storage.database import vector_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def parse_legacy_note(filepath: Path):
    """Parses legacy note_*.md markdown content."""
    text = filepath.read_text(encoding="utf-8")
    note_id = ""
    date_str = ""
    tags = []
    
    # Parse frontmatter
    fm_match = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        for line in fm_text.splitlines():
            if line.startswith("id:"):
                note_id = line.replace("id:", "").strip()
            elif line.startswith("date:"):
                date_str = line.replace("date:", "").strip()
            elif line.startswith("tags:"):
                raw_tags = line.replace("tags:", "").strip()
                tags = [t.strip().strip("'\"") for t in raw_tags.strip("[]").split(",") if t.strip()]

    # Extract summary (# Header)
    summary_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    summary = summary_match.group(1).strip() if summary_match else "Note"

    # Extract content
    content_match = re.search(r"\*\*Raw Input:\*\*\s*\n(.*)$", text, re.DOTALL)
    content = content_match.group(1).strip() if content_match else text

    # Parse date
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        dt = datetime.fromtimestamp(filepath.stat().st_mtime)

    return {
        "id": note_id,
        "date": dt,
        "tags": tags,
        "summary": summary,
        "content": content,
    }

def classify_legacy_note(summary: str, tags: list[str]) -> str:
    """Quick rule-based classification for legacy notes with fallback to Resources."""
    tag_lower = " ".join(tags).lower()
    sum_lower = summary.lower()
    combined = f"{tag_lower} {sum_lower}"

    if any(k in combined for k in ["greeting", "hello", "casual", "test"]):
        return "Archive"
    elif any(k in combined for k in ["profile", "identity", "date of birth", "trading", "stock", "finance", "expense", "grocery", "purchase"]):
        return "Areas"
    elif any(k in combined for k in ["task", "todo", "sprint", "project", "deadline"]):
        return "Projects"
    else:
        return "Resources"

def migrate_existing_storage():
    """Migrates flat files in Raw_Inbox and Processed_Wiki into organized folders."""
    logger.info("Starting Second Brain storage migration...")
    
    # Ensure all directories exist
    for cat in PARA_CATEGORIES:
        (WIKI_DIR / cat).mkdir(parents=True, exist_ok=True)
    for med in MEDIA_CATEGORIES:
        (STORAGE_DIR / med).mkdir(parents=True, exist_ok=True)

    # 1. Organize legacy media files in Raw_Inbox
    media_mapping = {}
    for media_file in list(STORAGE_DIR.iterdir()):
        if media_file.is_file() and not media_file.name.startswith("desktop.ini"):
            mtime = datetime.fromtimestamp(media_file.stat().st_mtime)
            month_folder = mtime.strftime("%Y-%m")
            date_prefix = mtime.strftime("%Y-%m-%d")
            
            ext = media_file.suffix.lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
                subfolder = "Images"
            elif ext in [".ogg", ".mp3", ".wav", ".m4a"]:
                subfolder = "Audio"
            else:
                subfolder = "Documents"

            dest_folder = STORAGE_DIR / subfolder / month_folder
            dest_folder.mkdir(parents=True, exist_ok=True)

            clean_slug = slugify(media_file.stem.replace("temp_", "").replace("screenshot_", "image-").replace("audio_", "audio-"))
            new_name = f"{date_prefix}_{clean_slug}{ext}"
            new_path = dest_folder / new_name

            # Avoid overwrite collision
            counter = 1
            while new_path.exists():
                new_path = dest_folder / f"{date_prefix}_{clean_slug}_{counter}{ext}"
                counter += 1

            shutil.move(media_file, new_path)
            media_mapping[media_file.name] = new_path
            logger.info(f"Moved media: {media_file.name} -> {new_path.relative_to(STORAGE_DIR.parent)}")

    # 2. Organize legacy markdown notes in Processed_Wiki root
    migrated_notes = 0
    for note_file in list(WIKI_DIR.glob("note_*.md")):
        data = parse_legacy_note(note_file)
        category = classify_legacy_note(data["summary"], data["tags"])
        slug = slugify(data["summary"])
        date_prefix = data["date"].strftime("%Y-%m-%d")
        timestamp = data["date"].strftime("%Y-%m-%d %H:%M:%S")

        target_dir = WIKI_DIR / category
        new_note_name = f"{date_prefix}_{slug}.md"
        new_note_path = target_dir / new_note_name

        counter = 1
        while new_note_path.exists():
            new_note_path = target_dir / f"{date_prefix}_{slug}_{counter}.md"
            counter += 1

        # Build clean markdown
        tag_list_str = ", ".join(f"#{t}" for t in data["tags"])
        markdown_content = (
            f"---\n"
            f"id: {data['id']}\n"
            f"date: {timestamp}\n"
            f"category: {category}\n"
            f"tags: {data['tags']}\n"
            f"media: \n"
            f"---\n\n"
            f"# {data['summary']}\n\n"
            f"> **Category:** {category} | **Date:** {date_prefix} | **Tags:** {tag_list_str}\n\n"
            f"**Raw Input:**\n"
            f"{data['content']}\n"
        )

        with open(new_note_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        # Remove old legacy note
        note_file.unlink()

        # Update Vector DB entry metadata
        if data["id"]:
            try:
                vector_db.update_document(
                    document_id=data["id"],
                    document=None # update metadata if supported
                )
            except Exception:
                pass

        logger.info(f"Migrated note: {note_file.name} -> {new_note_path.relative_to(WIKI_DIR.parent)}")
        migrated_notes += 1

    logger.info(f"Migration completed! {migrated_notes} notes migrated.")

if __name__ == "__main__":
    migrate_existing_storage()
