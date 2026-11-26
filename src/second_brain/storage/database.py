import os
from pathlib import Path
import uuid
import hashlib
import logging
from typing import Optional
from datetime import datetime
import chromadb
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings

logger = logging.getLogger(__name__)
from second_brain.config import (
    WIKI_DIR,
    STORAGE_DIR,
    STORAGE_BASE_DIR,
    GEMINI_API_KEY,
    PARA_CATEGORIES,
    CHROMA_DIR,
    CHROMA_SERVER_HOST,
    CHROMA_SERVER_PORT
)
from second_brain.core.ai import slugify

# Initialize the embedding model using the current standard
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001", 
    google_api_key=GEMINI_API_KEY
)

def _init_chroma_collection(collection_name: str) -> Chroma:
    """
    Initializes a Chroma collection.
    - If CHROMA_SERVER_HOST is configured, connects to central ChromaDB server (multi-worker safe).
    - Otherwise, runs in Embedded Mode using local CHROMA_DIR on disk.
    """
    if CHROMA_SERVER_HOST:
        client = chromadb.HttpClient(host=CHROMA_SERVER_HOST, port=CHROMA_SERVER_PORT)
        return Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            client=client
        )
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR)
    )

# Global fallback vector DB instance
vector_db = _init_chroma_collection("second_brain_notes")

# User-isolated ChromaDB collection cache
_user_collections: dict[str, Chroma] = {}

def get_user_vector_db(username: str) -> Chroma:
    """Retrieves or initializes an isolated Chroma vector database collection for the specific user."""
    safe_name = f"vault_{username.replace('-', '_').lower()}"
    if safe_name not in _user_collections:
        _user_collections[safe_name] = _init_chroma_collection(safe_name)
    return _user_collections[safe_name]

def compute_content_hash(content: str = "", media_path: Path | str = None) -> str:
    """Computes a deterministic SHA-256 hash of text content and optional media bytes for deduplication."""
    hasher = hashlib.sha256()
    clean_text = (content or "").strip()
    if clean_text:
        hasher.update(clean_text.encode("utf-8"))
    if media_path:
        mp = Path(media_path)
        if mp.exists() and mp.is_file():
            try:
                with open(mp, "rb") as f:
                    while chunk := f.read(65536):
                        hasher.update(chunk)
            except Exception:
                pass
    return hasher.hexdigest()

def check_duplicate_note(content: str = "", user: dict = None, media_path: Path | str = None) -> Optional[dict]:
    """Checks if a note with identical content or file hash already exists in user's vault."""
    try:
        content_hash = compute_content_hash(content, media_path)
        active_db = get_user_vector_db(user["username"]) if user and "username" in user else vector_db
        
        # 1. Query ChromaDB directly by content_hash or file_hash metadata
        try:
            results = active_db.get(where={"content_hash": content_hash})
            if results and results.get("ids") and len(results["ids"]) > 0:
                meta = results["metadatas"][0]
                return {
                    "id": results["ids"][0],
                    "summary": meta.get("summary", "Existing Note"),
                    "category": meta.get("category", "Resources"),
                    "file_path": meta.get("file_path", ""),
                    "rel_file_path": meta.get("rel_file_path", ""),
                    "content_hash": content_hash
                }
        except Exception:
            pass

        try:
            results = active_db.get(where={"file_hash": content_hash})
            if results and results.get("ids") and len(results["ids"]) > 0:
                meta = results["metadatas"][0]
                return {
                    "id": results["ids"][0],
                    "summary": meta.get("summary", "Existing Note"),
                    "category": meta.get("category", "Resources"),
                    "file_path": meta.get("file_path", ""),
                    "rel_file_path": meta.get("rel_file_path", ""),
                    "content_hash": content_hash
                }
        except Exception:
            pass

        # 2. Backward compatibility: check raw text matching in existing Chroma documents
        clean_text = (content or "").strip()
        if clean_text:
            all_docs = active_db.get()
            if all_docs and all_docs.get("documents"):
                for i, doc_text in enumerate(all_docs["documents"]):
                    doc_stripped = doc_text.strip()
                    if clean_text in doc_stripped or doc_stripped in clean_text or compute_content_hash(doc_stripped) == content_hash:
                        meta = all_docs["metadatas"][i]
                        return {
                            "id": all_docs["ids"][i],
                            "summary": meta.get("summary", "Existing Note"),
                            "category": meta.get("category", "Resources"),
                            "file_path": meta.get("file_path", ""),
                            "rel_file_path": meta.get("rel_file_path", ""),
                            "content_hash": content_hash
                        }
    except Exception:
        pass
    return None

def save_to_brain(
    content: str,
    summary: str,
    tags: list[str],
    category: str = "Resources",
    slug: str = None,
    media_path: Path | str = None,
    media_type: str = None,
    user: dict = None,
    content_hash: str = None
) -> Path:
    """Handles the dual-write to both File System (PARA folders) and Vector DB with tenant isolation."""
    note_id = str(uuid.uuid4())
    now = datetime.now()
    date_prefix = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # Compute deterministic SHA-256 hash for deduplication
    if not content_hash:
        content_hash = compute_content_hash(content, media_path)
    
    # 1. Normalize PARA category & determine user wiki dir
    valid_category = category if category in PARA_CATEGORIES else "Resources"
    target_wiki_base = user["wiki_dir"] if user and "wiki_dir" in user else WIKI_DIR
    target_dir = target_wiki_base / valid_category
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Compute descriptive filename
    note_slug = slugify(slug or summary)
    filename = target_dir / f"{date_prefix}_{note_slug}.md"
    if filename.exists():
        filename = target_dir / f"{date_prefix}_{note_slug}_{note_id[:4]}.md"
        
    # 3. Format media attachment reference if provided
    media_rel_link = ""
    attachment_block = ""
    if media_path:
        media_path = Path(media_path)
        try:
            media_rel_link = os.path.relpath(media_path, filename.parent).replace("\\", "/")
        except Exception:
            media_rel_link = str(media_path)
            
        media_name = media_path.name
        is_image = (media_type == "Images") or media_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
        is_audio = (media_type == "Audio") or media_name.lower().endswith((".ogg", ".mp3", ".m4a", ".wav"))
        is_pdf = media_name.lower().endswith(".pdf")
        
        if is_image:
            attachment_block = f"\n> 🖼️ **Attached Image:** [{media_name}]({media_rel_link})\n>\n> ![{media_name}]({media_rel_link})\n"
        elif is_audio:
            attachment_block = f"\n> 🎙️ **Attached Audio:** [{media_name}]({media_rel_link})\n"
        elif is_pdf:
            attachment_block = f"\n> 📄 **Attached PDF:** [{media_name}]({media_rel_link})\n"
        else:
            attachment_block = f"\n> 📎 **Attached Document:** [{media_name}]({media_rel_link})\n"

    # 4. Write to the Physical Folder (Markdown with frontmatter)
    tag_list_str = ", ".join(f"#{t}" for t in tags)
    markdown_content = (
        f"---\n"
        f"id: {note_id}\n"
        f"date: {timestamp}\n"
        f"category: {valid_category}\n"
        f"tags: {tags}\n"
        f"media: {media_rel_link}\n"
        f"hash: {content_hash}\n"
        f"---\n\n"
        f"# {summary}\n\n"
        f"> **Category:** {valid_category} | **Date:** {date_prefix} | **Tags:** {tag_list_str}\n"
        f"{attachment_block}\n"
        f"**Raw Input:**\n"
        f"{content}\n"
    )
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown_content)
        
    # 5. Write to the Vector Database (Scoped to user's collection)
    active_db = get_user_vector_db(user["username"]) if user and "username" in user else vector_db

    # Calculate portable relative paths across machines / cloud folders
    target_wiki_base = user["wiki_dir"] if user and "wiki_dir" in user else WIKI_DIR
    try:
        rel_file_path = str(filename.relative_to(target_wiki_base)).replace("\\", "/")
    except Exception:
        rel_file_path = filename.name

    rel_media_path = ""
    if media_path:
        user_storage = user["storage_dir"] if user and "storage_dir" in user else STORAGE_DIR
        try:
            rel_media_path = str(Path(media_path).relative_to(user_storage)).replace("\\", "/")
        except Exception:
            rel_media_path = Path(media_path).name

    active_db.add_texts(
        texts=[content],
        metadatas=[{
            "id": note_id,
            "summary": summary,
            "category": valid_category,
            "tags": ",".join(tags),
            "file_path": str(filename),
            "rel_file_path": rel_file_path,
            "media_path": str(media_path) if media_path else "",
            "rel_media_path": rel_media_path,
            "username": user["username"] if user and "username" in user else "default",
            "content_hash": content_hash,
            "file_hash": content_hash
        }],
        ids=[note_id]
    )
    return filename

def search_brain(query: str, k: int = 3, user: dict = None):
    """Performs a semantic search on the vector database scoped to the active user."""
    active_db = get_user_vector_db(user["username"]) if user and "username" in user else vector_db
    results = active_db.similarity_search(query, k=k)
    return results

def delete_note_from_brain(
    category: str,
    filename: str,
    user: dict,
    delete_attached_media: bool = False
) -> dict:
    """
    Safely deletes a note from both the physical storage and the vector database (ChromaDB).
    Guarantees no ghost embeddings remain for RAG queries.
    """
    user_wiki = user["wiki_dir"] if user and "wiki_dir" in user else WIKI_DIR
    target_dir = user_wiki / category
    note_path = target_dir / filename

    if not note_path.exists():
        for cat in PARA_CATEGORIES:
            candidate = user_wiki / cat / filename
            if candidate.exists():
                note_path = candidate
                category = cat
                break

    if not note_path.exists():
        raise FileNotFoundError(f"Note '{filename}' not found in vault category '{category}'.")

    note_id = None
    media_rel = None
    try:
        content = note_path.read_text(encoding="utf-8")
        in_fm = False
        for line in content.splitlines()[:30]:
            if line.strip() == "---":
                in_fm = not in_fm
                continue
            if in_fm:
                if line.startswith("id:"):
                    note_id = line.replace("id:", "").strip()
                elif line.startswith("media:"):
                    media_rel = line.replace("media:", "").strip()
    except Exception as e:
        logger.warning(f"Could not parse frontmatter from {note_path}: {e}")

    # 1. Delete from ChromaDB
    active_db = get_user_vector_db(user["username"]) if user and "username" in user else vector_db
    deleted_vector = False

    if note_id:
        try:
            active_db.delete(ids=[note_id])
            deleted_vector = True
        except Exception as e:
            logger.warning(f"Failed to delete ChromaDB entry by id {note_id}: {e}")

    if not deleted_vector:
        try:
            rel_path = f"{category}/{filename}"
            matches = active_db.get(where={"rel_file_path": rel_path})
            if matches and matches.get("ids"):
                active_db.delete(ids=matches["ids"])
                deleted_vector = True
        except Exception:
            pass

    # 2. Delete physical Markdown file
    note_path.unlink()

    # 3. Optional: Delete attached media if requested and inside user storage
    deleted_media_path = None
    if delete_attached_media and media_rel:
        user_storage = user["storage_dir"] if user and "storage_dir" in user else STORAGE_DIR
        try:
            possible_media = (note_path.parent / media_rel).resolve()
            if possible_media.exists() and possible_media.is_file():
                if user_storage.resolve() in possible_media.parents:
                    possible_media.unlink()
                    deleted_media_path = str(possible_media)
        except Exception as e:
            logger.warning(f"Failed to delete media {media_rel}: {e}")

    return {
        "success": True,
        "filename": filename,
        "category": category,
        "note_id": note_id,
        "vector_purged": deleted_vector,
        "media_deleted": deleted_media_path
    }
