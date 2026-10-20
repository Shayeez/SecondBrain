import os
import shutil
import uuid
import logging
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    Query,
    Depends,
    Request,
    Response,
    status
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from second_brain.config import (
    STORAGE_DIR,
    WIKI_DIR,
    CHROMA_DIR,
    PARA_CATEGORIES,
    MEDIA_CATEGORIES,
    WEB_HOST,
    WEB_PORT,
    BRAIN_AUTH_TOKEN,
    _resolve_cross_platform_path
)
from second_brain.core.ai import process_thought, generate_rag_answer, slugify
from second_brain.storage.database import save_to_brain, search_brain, vector_db, get_user_vector_db
from second_brain.core.users import get_user_by_token, get_user_storage_metrics, check_user_quota

logger = logging.getLogger("second_brain.web")
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

app = FastAPI(
    title="Second Brain Web Interface",
    description="In-house multimodal knowledge capture, retrieval, and RAG interface",
    version="1.0.0"
)

# Enable CORS for flexible local development and remote access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths for static assets
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# --- Authentication & Brute-Force Rate Limiting ---
FAILED_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 60

def check_login_rate_limit(client_ip: str):
    """Enforces a rate limit on failed login attempts per IP address."""
    now = time.time()
    if client_ip in FAILED_LOGIN_ATTEMPTS:
        recent = [t for t in FAILED_LOGIN_ATTEMPTS[client_ip] if now - t < LOCKOUT_WINDOW_SECONDS]
        FAILED_LOGIN_ATTEMPTS[client_ip] = recent
        if len(recent) >= MAX_FAILED_ATTEMPTS:
            remaining = int(LOCKOUT_WINDOW_SECONDS - (now - recent[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts. Access temporarily locked for {max(1, remaining)}s."
            )

def record_failed_attempt(client_ip: str):
    now = time.time()
    if client_ip not in FAILED_LOGIN_ATTEMPTS:
        FAILED_LOGIN_ATTEMPTS[client_ip] = []
    FAILED_LOGIN_ATTEMPTS[client_ip].append(now)

def clear_failed_attempts(client_ip: str):
    if client_ip in FAILED_LOGIN_ATTEMPTS:
        del FAILED_LOGIN_ATTEMPTS[client_ip]

def extract_request_token(request: Request) -> Optional[str]:
    """Extracts authentication token from cookie, headers, or query parameters."""
    cookie_token = request.cookies.get("brain_session_token")
    if cookie_token:
        return cookie_token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_token = request.headers.get("X-Brain-Token")
    if x_token:
        return x_token.strip()

    q_token = request.query_params.get("token") or request.query_params.get("auth")
    if q_token:
        return q_token.strip()

    return None

async def require_user(request: Request) -> dict:
    """
    Dependency that resolves and enforces authentication for the specific user.
    Returns the user profile dictionary with isolated storage paths.
    """
    token = extract_request_token(request)
    user = get_user_by_token(token)
    if user:
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Valid user access key or passphrase required"
    )

# Alias for backwards compatibility
require_auth = require_user

# --- Authentication & PWA Endpoints ---
@app.post("/api/auth/login")
async def api_auth_login(request: Request, response: Response):
    """Verifies passphrase and returns an authenticated session cookie and user profile."""
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip)

    token = ""
    try:
        body = await request.json()
        token = str(body.get("token", "")).strip()
    except Exception:
        pass

    user = get_user_by_token(token)
    if not user:
        record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access key or passphrase."
        )

    clear_failed_attempts(client_ip)
    
    # Set HTTP-only session cookie (valid for 30 days)
    response.set_cookie(
        key="brain_session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
        path="/"
    )
    return {
        "success": True,
        "authenticated": True,
        "token": token,
        "user": {
            "username": user["username"],
            "display_name": user["display_name"],
            "max_storage_mb": user["max_storage_mb"]
        }
    }

@app.get("/api/auth/verify")
async def api_auth_verify(request: Request):
    """Checks whether the client has valid authentication and returns active user."""
    token = extract_request_token(request)
    user = get_user_by_token(token)
    if user:
        return {
            "authenticated": True,
            "auth_required": True,
            "user": {
                "username": user["username"],
                "display_name": user["display_name"],
                "max_storage_mb": user["max_storage_mb"]
            }
        }

    return {"authenticated": False, "auth_required": True}

@app.post("/api/auth/logout")
async def api_auth_logout(response: Response):
    """Terminates session by clearing the authentication cookie."""
    response.delete_cookie(key="brain_session_token", path="/")
    return {"success": True, "authenticated": False}

@app.get("/manifest.json")
async def serve_manifest():
    """Serves the PWA manifest."""
    manifest_path = STATIC_DIR / "manifest.json"
    if manifest_path.exists():
        return FileResponse(manifest_path, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="Manifest not found")

@app.get("/sw.js")
async def serve_service_worker():
    """Serves the PWA service worker."""
    sw_path = STATIC_DIR / "sw.js"
    if sw_path.exists():
        return FileResponse(sw_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Service worker not found")


def format_gdrive_path(path: Path | str, user: Optional[dict] = None) -> str:
    """Formats a system file path into a clean, platform-independent vault path."""
    if not path:
        return ""
    p = Path(path)
    parts = p.parts
    for i, part in enumerate(parts):
        if part.lower() in ["secondbrain", "users"]:
            return "/".join(parts[i:])
    try:
        ref_parent = user["user_root"].parent if user and "user_root" in user else WIKI_DIR.parent
        return f"SecondBrain/{p.relative_to(ref_parent)}".replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")

def resolve_secure_path(path_str: str, user: Optional[dict] = None) -> Optional[Path]:
    """
    Resolves and strictly validates that a path is safe to access within the user's isolated storage.
    Guarantees cross-tenant isolation and prevents path traversal.
    """
    if not path_str:
        return None

    user_storage = user["storage_dir"] if user and "storage_dir" in user else STORAGE_DIR
    user_wiki = user["wiki_dir"] if user and "wiki_dir" in user else WIKI_DIR
    user_root = user["user_root"] if user and "user_root" in user else None

    resolved = _resolve_cross_platform_path(path_str)
    
    # 1. Direct path check (Must be inside user_root if user is provided)
    if resolved.exists() and resolved.is_file():
        if user_root:
            try:
                resolved.resolve().relative_to(user_root.resolve())
                return resolved
            except ValueError:
                pass
        else:
            return resolved

    # 2. Check relative to user_storage
    clean_rel = path_str.lstrip("/\\")
    candidate_storage = user_storage / clean_rel
    if candidate_storage.exists() and candidate_storage.is_file():
        return candidate_storage

    # 3. Check relative to user_wiki
    candidate_wiki = user_wiki / clean_rel
    if candidate_wiki.exists() and candidate_wiki.is_file():
        return candidate_wiki

    # 4. Search by basename strictly within the user's isolated directories
    target_name = Path(path_str).name
    if target_name:
        for f in user_wiki.rglob(target_name):
            if f.is_file():
                return f
        for f in user_storage.rglob(target_name):
            if f.is_file():
                return f

    return None

def detect_media_type(filename: str, content_type: Optional[str] = None) -> tuple[str, str]:
    """Detects category (Images, Audio, Documents) and normalized extension."""
    ext = os.path.splitext(filename)[1].lower() if filename else ""
    c_type = (content_type or "").lower()

    if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"] or c_type.startswith("image/"):
        norm_ext = ext if ext else ".jpg"
        return "Images", norm_ext
    elif ext in [".ogg", ".mp3", ".wav", ".m4a", ".webm", ".aac", ".flac"] or c_type.startswith("audio/"):
        norm_ext = ext if ext else ".webm"
        return "Audio", norm_ext
    else:
        norm_ext = ext if ext else ".pdf"
        return "Documents", norm_ext

@app.get("/api/stats")
async def get_system_stats(user: dict = Depends(require_user)):
    """Returns statistics about notes in the PARA framework and storage quota for active user."""
    user_wiki = user["wiki_dir"]
    user_storage = user["storage_dir"]

    para_counts = {}
    total_notes = 0
    for category in PARA_CATEGORIES:
        cat_dir = user_wiki / category
        count = len(list(cat_dir.glob("*.md"))) if cat_dir.exists() else 0
        para_counts[category] = count
        total_notes += count

    media_counts = {}
    for med in MEDIA_CATEGORIES:
        med_dir = user_storage / med
        count = len([f for f in med_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]) if med_dir.exists() else 0
        media_counts[med] = count

    vector_count = 0
    try:
        user_db = get_user_vector_db(user["username"])
        col = user_db._collection
        vector_count = col.count() if col else 0
    except Exception:
        vector_count = total_notes

    metrics = get_user_storage_metrics(user)

    return {
        "status": "online",
        "user": {
            "username": user["username"],
            "display_name": user["display_name"]
        },
        "storage_metrics": metrics,
        "total_notes": total_notes,
        "para_counts": para_counts,
        "media_counts": media_counts,
        "vector_embeddings": vector_count,
        "storage_dir": format_gdrive_path(user_storage, user=user),
        "wiki_dir": format_gdrive_path(user_wiki, user=user)
    }

@app.get("/api/notes")
async def list_notes(
    limit: int = 50,
    category: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_user)
):
    """Lists recent notes with metadata strictly within the authenticated user's vault."""
    user_wiki = user["wiki_dir"]
    notes = []
    categories_to_search = [category] if category and category in PARA_CATEGORIES else PARA_CATEGORIES

    for cat in categories_to_search:
        cat_dir = user_wiki / cat
        if not cat_dir.exists():
            continue
        for md_file in cat_dir.glob("*.md"):
            try:
                stat = md_file.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                
                # Parse title from first # header or filename
                summary = md_file.stem
                tags = []
                media_path = ""
                
                lines = content.splitlines()
                for line in lines:
                    if line.startswith("# "):
                        summary = line[2:].strip()
                        break

                # Extract frontmatter tags & media
                in_fm = False
                for line in lines[:25]:
                    if line.strip() == "---":
                        in_fm = not in_fm
                        continue
                    if in_fm:
                        if line.startswith("tags:"):
                            raw_tags = line.replace("tags:", "").strip()
                            tags = [t.strip().strip("'\"") for t in raw_tags.strip("[]").split(",") if t.strip()]
                        elif line.startswith("media:"):
                            media_path = line.replace("media:", "").strip()

                if search:
                    q = search.lower()
                    if q not in summary.lower() and q not in content.lower() and not any(q in t.lower() for t in tags):
                        continue

                notes.append({
                    "id": md_file.stem,
                    "filename": md_file.name,
                    "summary": summary,
                    "category": cat,
                    "tags": tags,
                    "mtime": mtime.strftime("%Y-%m-%d %H:%M"),
                    "timestamp": stat.st_mtime,
                    "has_media": bool(media_path),
                    "media_link": f"/api/file/view?path={media_path}" if media_path else None,
                    "view_url": f"/api/note/{cat}/{md_file.name}",
                    "download_url": f"/api/file/view?path={md_file}&download=true"
                })
            except Exception as e:
                logger.warning(f"Error reading note {md_file}: {e}")

    # Sort newest first
    notes.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"notes": notes[:limit], "total": len(notes)}

@app.get("/api/note/{category}/{filename}")
async def get_note_detail(category: str, filename: str, user: dict = Depends(require_user)):
    """Returns markdown text and details of a single note within the user's vault."""
    if category not in PARA_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    
    note_path = user["wiki_dir"] / category / filename
    if not note_path.exists() or not note_path.is_file():
        raise HTTPException(status_code=404, detail="Note not found")

    content = note_path.read_text(encoding="utf-8")
    return {
        "filename": filename,
        "category": category,
        "gdrive_path": format_gdrive_path(note_path, user=user),
        "content": content
    }

@app.get("/api/file/view")
async def view_or_download_file(
    path: str = Query(...),
    download: bool = Query(False),
    user: dict = Depends(require_user)
):
    """Safely serves raw media or note files strictly isolated to the authenticated user."""
    file_path = resolve_secure_path(path, user=user)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    filename = file_path.name
    _, ext = detect_media_type(filename)
    
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    else:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'

    return FileResponse(path=file_path, filename=filename if download else None, headers=headers)

@app.post("/api/ask")
async def ask_query(payload: dict, user: dict = Depends(require_user)):
    """Conversational RAG search endpoint scoped strictly to the active user's vector space."""
    query = payload.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    docs = search_brain(query, k=4, user=user)
    if not docs:
        return {
            "answer": "I couldn't find any relevant notes or files in your Second Brain for that question.",
            "sources": []
        }

    answer = generate_rag_answer(query, docs)
    sources = []
    for doc in docs:
        summary = doc.metadata.get("summary", "Untitled")
        category = doc.metadata.get("category", "Resources")
        file_path = doc.metadata.get("file_path", "")
        media_path = doc.metadata.get("media_path", "")
        
        sources.append({
            "summary": summary,
            "category": category,
            "gdrive_path": format_gdrive_path(file_path, user=user),
            "media_gdrive": format_gdrive_path(media_path, user=user) if media_path else "",
            "file_url": f"/api/file/view?path={file_path}" if file_path else "",
            "media_url": f"/api/file/view?path={media_path}" if media_path else "",
            "snippet": doc.page_content[:250] + ("..." if len(doc.page_content) > 250 else "")
        })

    return {
        "answer": answer,
        "sources": sources
    }

@app.post("/api/capture")
async def capture_input(
    text: Optional[str] = Form(""),
    mode: Optional[str] = Form("auto"),  # "auto", "note", "ask", "get"
    file: Optional[UploadFile] = File(None),
    user: dict = Depends(require_user)
):
    """
    Unified multimodal input endpoint with isolated user storage and quota limits:
    - Text thoughts, questions, or command strings
    - Media uploads: Images, Audio, Voice notes, Documents (PDFs)
    - Direct voice recording from browser
    """
    user_text = (text or "").strip()
    temp_media_path = None
    media_type = None
    media_ext = None
    original_filename = ""

    # Process file upload if provided
    if file and file.filename:
        # Check storage quota before reading file
        check_user_quota(user)
        
        original_filename = file.filename
        media_type, media_ext = detect_media_type(original_filename, file.content_type)
        temp_id = uuid.uuid4().hex[:8]
        temp_filename = f"temp_web_{temp_id}{media_ext}"
        temp_media_path = Path(temp_filename)
        
        try:
            with open(temp_media_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            logger.error(f"Failed to save uploaded file: {e}")
            raise HTTPException(status_code=500, detail="Failed to process uploaded file")

        # Re-check quota with actual file size on disk
        check_user_quota(user, incoming_bytes=temp_media_path.stat().st_size)

    # Command shortcuts handling (e.g., if user typed "/ask ..." or "/get ...")
    if user_text.startswith("/ask"):
        mode = "ask"
        user_text = user_text[4:].strip()
    elif user_text.startswith("/get") or user_text.startswith("/fetch"):
        mode = "get"
        user_text = user_text.split(" ", 1)[1].strip() if " " in user_text else ""

    if not user_text and not temp_media_path:
        raise HTTPException(status_code=400, detail="Please provide text or attach a file/audio.")

    try:
        # MODE 1: Direct Ask / RAG
        if mode == "ask":
            docs = search_brain(user_text, k=4, user=user)
            if not docs:
                return {
                    "type": "query",
                    "query": user_text,
                    "answer": "I couldn't find any relevant notes in your Second Brain for that question.",
                    "sources": []
                }
            answer = generate_rag_answer(user_text, docs)
            sources = []
            for doc in docs:
                file_p = doc.metadata.get("file_path", "")
                media_p = doc.metadata.get("media_path", "")
                sources.append({
                    "summary": doc.metadata.get("summary", "Untitled"),
                    "category": doc.metadata.get("category", "Resources"),
                    "gdrive_path": format_gdrive_path(file_p, user=user),
                    "media_gdrive": format_gdrive_path(media_p, user=user),
                    "file_url": f"/api/file/view?path={file_p}" if file_p else None,
                    "media_url": f"/api/file/view?path={media_p}" if media_p else None,
                    "snippet": doc.page_content[:250] + ("..." if len(doc.page_content) > 250 else "")
                })
            return {
                "type": "query",
                "query": user_text,
                "answer": answer,
                "sources": sources
            }

        # MODE 2: Direct File Retrieval / Fetch
        if mode == "get":
            docs = search_brain(user_text, k=4, user=user)
            if not docs:
                return {
                    "type": "retrieval",
                    "found": False,
                    "message": f"No documents or notes found matching: '{user_text}'"
                }

            # Select matching item, preferring one with attached media
            matched_doc = None
            for doc in docs:
                m_p = doc.metadata.get("media_path")
                if m_p and resolve_secure_path(m_p, user=user):
                    matched_doc = doc
                    break
            if not matched_doc:
                matched_doc = docs[0]

            summary = matched_doc.metadata.get("summary", "Document")
            category = matched_doc.metadata.get("category", "Resources")
            f_path = matched_doc.metadata.get("file_path", "")
            m_path = matched_doc.metadata.get("media_path", "")
            
            resolved_m = resolve_secure_path(m_path, user=user) if m_path else None
            resolved_f = resolve_secure_path(f_path, user=user) if f_path else None

            return {
                "type": "retrieval",
                "found": True,
                "summary": summary,
                "category": category,
                "note_gdrive": format_gdrive_path(f_path, user=user),
                "media_gdrive": format_gdrive_path(m_path, user=user) if m_path else None,
                "note_url": f"/api/file/view?path={f_path}&download=true" if resolved_f else None,
                "media_url": f"/api/file/view?path={m_path}&download=true" if resolved_m else None,
                "preview_url": f"/api/file/view?path={m_path}" if resolved_m else None,
                "media_name": resolved_m.name if resolved_m else None
            }

        # MODE 3 & 4: Auto (AI-routed) or Forced Note Save
        ai_result = process_thought(text=user_text, media_path=str(temp_media_path) if temp_media_path else None)

        if mode == "auto" and ai_result.get("intent") == "QUERY":
            query = ai_result.get("query", user_text)
            docs = search_brain(query, k=4, user=user)
            if not docs:
                return {
                    "type": "query",
                    "query": query,
                    "answer": f"I couldn't find any relevant notes in your brain for: '{query}'",
                    "sources": []
                }
            answer = generate_rag_answer(query, docs)
            sources = []
            matched_media = None
            retrieval_keywords = ["send", "get", "fetch", "download", "give me", "show me", "document", "pdf", "file", "receipt", "invoice"]
            wants_file = any(k in query.lower() for k in retrieval_keywords)

            for doc in docs:
                f_p = doc.metadata.get("file_path", "")
                m_p = doc.metadata.get("media_path", "")
                resolved_m = resolve_secure_path(m_p, user=user) if m_p else None
                if wants_file and resolved_m and not matched_media:
                    matched_media = {
                        "name": resolved_m.name,
                        "url": f"/api/file/view?path={m_p}&download=true",
                        "preview_url": f"/api/file/view?path={m_p}",
                        "gdrive_path": format_gdrive_path(m_p, user=user)
                    }
                sources.append({
                    "summary": doc.metadata.get("summary", "Untitled"),
                    "category": doc.metadata.get("category", "Resources"),
                    "gdrive_path": format_gdrive_path(f_p, user=user),
                    "media_gdrive": format_gdrive_path(m_p, user=user),
                    "file_url": f"/api/file/view?path={f_p}" if f_p else None,
                    "media_url": f"/api/file/view?path={m_p}" if m_p else None,
                    "snippet": doc.page_content[:250] + ("..." if len(doc.page_content) > 250 else "")
                })

            return {
                "type": "query",
                "query": query,
                "answer": answer,
                "sources": sources,
                "matched_file": matched_media
            }

        # Otherwise, SAVE intent into the user's isolated vault
        summary = ai_result.get("summary", "Quick Note")
        category = ai_result.get("category", "Resources")
        slug = ai_result.get("slug") or slugify(summary)
        tags = ai_result.get("tags", ["note"])
        final_content = ai_result.get("content", user_text)

        saved_media_path = None
        if temp_media_path and temp_media_path.exists():
            now = datetime.now()
            month_folder = now.strftime("%Y-%m")
            date_str = now.strftime("%Y-%m-%d")
            dest_dir = user["storage_dir"] / media_type / month_folder
            dest_dir.mkdir(parents=True, exist_ok=True)

            short_id = uuid.uuid4().hex[:4]
            dest_filename = f"{date_str}_{slug}_{short_id}{media_ext}"
            dest_path = dest_dir / dest_filename
            shutil.move(str(temp_media_path), str(dest_path))
            saved_media_path = dest_path
            temp_media_path = None  # Prevent deletion in finally

        # Save note to Processed_Wiki under the user's PARA folder
        note_filepath = save_to_brain(
            content=final_content,
            summary=summary,
            tags=tags,
            category=category,
            slug=slug,
            media_path=saved_media_path,
            media_type=media_type,
            user=user
        )

        return {
            "type": "saved",
            "summary": summary,
            "category": category,
            "tags": tags,
            "slug": slug,
            "content": final_content,
            "note_gdrive": format_gdrive_path(note_filepath, user=user),
            "media_gdrive": format_gdrive_path(saved_media_path, user=user) if saved_media_path else None,
            "note_url": f"/api/file/view?path={note_filepath}",
            "note_download": f"/api/file/view?path={note_filepath}&download=true",
            "media_url": f"/api/file/view?path={saved_media_path}" if saved_media_path else None,
            "media_download": f"/api/file/view?path={saved_media_path}&download=true" if saved_media_path else None,
            "media_type": media_type
        }

    finally:
        # Clean up temporary file if still exists
        if temp_media_path and temp_media_path.exists():
            try:
                temp_media_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete temp media {temp_media_path}: {e}")

# Mount static folder
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serves the main application page."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Second Brain Web is initializing...</h1>", status_code=200)
    return HTMLResponse(index_file.read_text(encoding="utf-8"))

def start_web_server(host: str = WEB_HOST, port: int = WEB_PORT):
    """Entry point to launch the web interface."""
    logger.info(f"Starting Second Brain Web Server on http://{host}:{port} ...")
    uvicorn.run("second_brain.interface.web_server:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    start_web_server()
