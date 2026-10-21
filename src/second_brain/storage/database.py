import os
from pathlib import Path
import uuid
from datetime import datetime
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from second_brain.config import WIKI_DIR, GEMINI_API_KEY, PARA_CATEGORIES, CHROMA_DIR
from second_brain.core.ai import slugify

# Initialize the embedding model using the current standard
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001", 
    google_api_key=GEMINI_API_KEY
)

# Initialize ChromaDB using absolute CHROMA_DIR path
vector_db = Chroma(
    collection_name="second_brain_notes",
    embedding_function=embeddings,
    persist_directory=str(CHROMA_DIR)
)

# User-isolated ChromaDB collection cache
_user_collections: dict[str, Chroma] = {}

def get_user_vector_db(username: str) -> Chroma:
    """Retrieves or initializes an isolated Chroma vector database collection for the specific user."""
    safe_name = f"vault_{username.replace('-', '_').lower()}"
    if safe_name not in _user_collections:
        _user_collections[safe_name] = Chroma(
            collection_name=safe_name,
            embedding_function=embeddings,
            persist_directory=str(CHROMA_DIR)
        )
    return _user_collections[safe_name]

def save_to_brain(
    content: str,
    summary: str,
    tags: list[str],
    category: str = "Resources",
    slug: str = None,
    media_path: Path | str = None,
    media_type: str = None,
    user: dict = None
) -> Path:
    """Handles the dual-write to both File System (PARA folders) and Vector DB with tenant isolation."""
    note_id = str(uuid.uuid4())
    now = datetime.now()
    date_prefix = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    
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
    active_db.add_texts(
        texts=[content],
        metadatas=[{
            "id": note_id,
            "summary": summary,
            "category": valid_category,
            "tags": ",".join(tags),
            "file_path": str(filename),
            "media_path": str(media_path) if media_path else ""
        }],
        ids=[note_id]
    )
    return filename

def search_brain(query: str, k: int = 3, user: dict = None):
    """Performs a semantic search on the vector database scoped to the active user."""
    active_db = get_user_vector_db(user["username"]) if user and "username" in user else vector_db
    results = active_db.similarity_search(query, k=k)
    return results