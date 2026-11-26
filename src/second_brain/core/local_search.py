"""
Cross-Platform Local Machine File Search & On-Demand Inspection Engine.
Operates across macOS, Linux, and Windows using Python's built-in SQLite FTS5.

Tier 1: High-speed sub-millisecond metadata search (filename, path, extension, dates).
Tier 2: On-demand AI inspection (opens and reads candidate files live to answer questions).
"""

import os
import re
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from second_brain.config import (
    LOCAL_INDEX_DB_PATH,
    LOCAL_SEARCH_DIRS,
    DEFAULT_EXCLUDED_DIRS,
    STORAGE_BASE_DIR,
    _resolve_cross_platform_path
)
from second_brain.core.ai import process_thought, query_local_llm, llm, USE_LOCAL_LLM, LOCAL_LLM_MODEL

logger = logging.getLogger("second_brain.local_search")


def get_db_connection(db_path: Path = LOCAL_INDEX_DB_PATH) -> sqlite3.Connection:
    """Creates a thread-safe connection to the local SQLite FTS5 index."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_fts_db(db_path: Path = LOCAL_INDEX_DB_PATH):
    """Initializes the SQLite tables and FTS5 full-text search index."""
    with get_db_connection(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS file_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT NOT NULL,
            parent_dir TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime REAL NOT NULL,
            indexed_at REAL NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
            filename,
            filepath,
            parent_dir,
            extension,
            content='file_records',
            content_rowid='id'
        );

        -- Sync triggers between master table and FTS index
        CREATE TRIGGER IF NOT EXISTS trg_files_ai AFTER INSERT ON file_records BEGIN
            INSERT INTO file_fts(rowid, filename, filepath, parent_dir, extension)
            VALUES (new.id, new.filename, new.filepath, new.parent_dir, new.extension);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_files_ad AFTER DELETE ON file_records BEGIN
            INSERT INTO file_fts(file_fts, rowid, filename, filepath, parent_dir, extension)
            VALUES ('delete', old.id, old.filename, old.filepath, old.parent_dir, old.extension);
        END;

        CREATE TRIGGER IF NOT EXISTS trg_files_au AFTER UPDATE ON file_records BEGIN
            INSERT INTO file_fts(file_fts, rowid, filename, filepath, parent_dir, extension)
            VALUES ('delete', old.id, old.filename, old.filepath, old.parent_dir, old.extension);
            INSERT INTO file_fts(rowid, filename, filepath, parent_dir, extension)
            VALUES (new.id, new.filename, new.filepath, new.parent_dir, new.extension);
        END;

        CREATE INDEX IF NOT EXISTS idx_files_mtime ON file_records(mtime);
        CREATE INDEX IF NOT EXISTS idx_files_ext ON file_records(extension);
        """)
        conn.commit()


# ==============================================================================
# Tier 1: Fast Filesystem Scanning & Metadata Indexing
# ==============================================================================

def scan_directory(
    root_path: Path | str,
    db_path: Path = LOCAL_INDEX_DB_PATH,
    max_depth: int = 8,
    batch_size: int = 500
) -> Dict[str, int]:
    """
    Crawls a local folder and incrementally updates the SQLite FTS5 database.
    Ignores common junk/cache/system folders. Fast: indexes ~10,000 files/sec.
    """
    root = Path(root_path).resolve()
    if not root.exists() or not root.is_dir():
        logger.warning(f"Scan directory does not exist: {root}")
        return {"scanned": 0, "inserted": 0, "updated": 0, "errors": 0}

    init_fts_db(db_path)
    now_ts = datetime.now().timestamp()

    inserted = 0
    updated = 0
    scanned = 0
    errors = 0

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Pre-fetch existing paths and modification times to do fast diffing
    cursor.execute("SELECT filepath, mtime FROM file_records WHERE filepath LIKE ?", (f"{str(root)}%",))
    existing_records = {row["filepath"]: row["mtime"] for row in cursor.fetchall()}

    batch_to_insert = []
    batch_to_update = []
    seen_paths = set()

    try:
        for current_root, dirs, files in os.walk(str(root)):
            # Prune excluded directories in-place so os.walk skips descending
            dirs[:] = [
                d for d in dirs
                if d not in DEFAULT_EXCLUDED_DIRS and not d.startswith(".")
            ]

            # Check depth limit
            rel_parts = Path(current_root).relative_to(root).parts
            if len(rel_parts) > max_depth:
                dirs.clear()
                continue

            for fname in files:
                if fname.startswith((".", "~$")):
                    continue

                scanned += 1
                fpath = os.path.join(current_root, fname)
                seen_paths.add(fpath)

                try:
                    stat = os.stat(fpath)
                    mtime = stat.st_mtime
                    size = stat.st_size
                    ext = os.path.splitext(fname)[1].lower()

                    if fpath not in existing_records:
                        batch_to_insert.append((fpath, fname, ext, current_root, size, mtime, now_ts))
                    elif mtime > existing_records[fpath]:
                        batch_to_update.append((fname, ext, current_root, size, mtime, now_ts, fpath))

                    # Flush insert batch
                    if len(batch_to_insert) >= batch_size:
                        cursor.executemany(
                            "INSERT OR IGNORE INTO file_records (filepath, filename, extension, parent_dir, size_bytes, mtime, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            batch_to_insert
                        )
                        inserted += len(batch_to_insert)
                        batch_to_insert.clear()

                    # Flush update batch
                    if len(batch_to_update) >= batch_size:
                        cursor.executemany(
                            "UPDATE file_records SET filename=?, extension=?, parent_dir=?, size_bytes=?, mtime=?, indexed_at=? WHERE filepath=?",
                            batch_to_update
                        )
                        updated += len(batch_to_update)
                        batch_to_update.clear()

                except (OSError, PermissionError):
                    errors += 1
                    continue

        # Flush remaining
        if batch_to_insert:
            cursor.executemany(
                "INSERT OR IGNORE INTO file_records (filepath, filename, extension, parent_dir, size_bytes, mtime, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                batch_to_insert
            )
            inserted += len(batch_to_insert)

        if batch_to_update:
            cursor.executemany(
                "UPDATE file_records SET filename=?, extension=?, parent_dir=?, size_bytes=?, mtime=?, indexed_at=? WHERE filepath=?",
                batch_to_update
            )
            updated += len(batch_to_update)

        # Prune deleted files that were in this root
        deleted_paths = [p for p in existing_records if p not in seen_paths]
        if deleted_paths:
            cursor.executemany("DELETE FROM file_records WHERE filepath=?", [(p,) for p in deleted_paths])

        conn.commit()
    finally:
        conn.close()

    return {
        "scanned": scanned,
        "inserted": inserted,
        "updated": updated,
        "deleted": len(deleted_paths) if 'deleted_paths' in locals() else 0,
        "errors": errors
    }


def scan_all_configured_dirs(
    directories: Optional[List[Path]] = None,
    db_path: Path = LOCAL_INDEX_DB_PATH
) -> Dict[str, Any]:
    """Scans all configured user directories and logs summary."""
    dirs_to_scan = directories or LOCAL_SEARCH_DIRS
    summary = {"scanned": 0, "inserted": 0, "updated": 0, "deleted": 0, "errors": 0, "directories": []}

    for d in dirs_to_scan:
        res = scan_directory(d, db_path=db_path)
        summary["directories"].append({"dir": str(d), **res})
        summary["scanned"] += res["scanned"]
        summary["inserted"] += res["inserted"]
        summary["updated"] += res["updated"]
        summary["deleted"] += res.get("deleted", 0)
        summary["errors"] += res["errors"]

    return summary


# ==============================================================================
# Tier 1 Search: Fast FTS5 Query Engine
# ==============================================================================

COMMON_QUESTION_STOPWORDS = {
    'what', 'how', 'why', 'when', 'where', 'who', 'which', 'does', 'do', 'did',
    'is', 'are', 'was', 'were', 'have', 'has', 'had', 'the', 'a', 'an', 'in',
    'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'and', 'or', 'about',
    'inside', 'this', 'that', 'these', 'those', 'can', 'could', 'would', 'should',
    'tell', 'me', 'show', 'contain', 'contains', 'contents', 'find', 'locate',
    'search', 'get', 'give', 'detail', 'details', 'check', 'please'
}

def _extract_candidate_terms(query: str) -> tuple[str, Optional[str]]:
    """
    Extracts high-signal search terms from natural language queries.
    1. Detects explicit filename tokens like ovhserverQuickStart.md or config.json.
    2. Filters out conversational question stopwords.
    Returns: (cleaned_search_term, optional_detected_extension)
    """
    clean_raw = query.strip()
    file_matches = re.findall(r'[\w\.-]+\.[a-zA-Z0-9]{1,5}', clean_raw)
    if file_matches:
        full_match = file_matches[0]
        if "." in full_match:
            stem, ext = full_match.rsplit(".", 1)
            return stem, f".{ext.lower()}"
        return full_match, None

    clean = re.sub(r'[^\w\s-]', ' ', clean_raw).strip()
    words = [w for w in clean.split() if w.lower() not in COMMON_QUESTION_STOPWORDS and len(w) > 1]
    if words:
        return " ".join(words), None
    return clean_raw, None

def _sanitize_fts_query(query: str) -> str:
    """Prepares text into safe FTS5 token expression."""
    clean = re.sub(r'[^\w\s-]', ' ', query).strip()
    tokens = clean.split()
    if not tokens:
        return ""
    return " AND ".join(f'"{t}"*' for t in tokens if len(t) > 0)


def search_local_files(
    query: str,
    limit: int = 20,
    extension: Optional[str] = None,
    db_path: Path = LOCAL_INDEX_DB_PATH
) -> List[Dict[str, Any]]:
    """
    Performs sub-millisecond BM25 ranking search across the local machine filesystem.
    Gracefully handles conversational questions, natural language, and exact filenames.
    """
    init_fts_db(db_path)
    clean_term, detected_ext = _extract_candidate_terms(query)
    effective_ext = extension or detected_ext

    fts_queries_to_try = []
    if clean_term != query:
        fts_queries_to_try.append(_sanitize_fts_query(clean_term))
    fts_queries_to_try.append(_sanitize_fts_query(query))

    results = []
    seen_ids = set()

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    try:
        # 1. Try FTS query with clean extracted terms
        for fts_q in fts_queries_to_try:
            if not fts_q:
                continue
            sql = """
                SELECT r.id, r.filepath, r.filename, r.extension, r.parent_dir, r.size_bytes, r.mtime,
                       bm25(file_fts) as rank
                FROM file_fts f
                JOIN file_records r ON f.rowid = r.id
                WHERE file_fts MATCH ?
            """
            params = [fts_q]
            if effective_ext:
                norm_ext = f".{effective_ext.lstrip('.')}".lower()
                sql += " AND r.extension = ?"
                params.append(norm_ext)

            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            cursor.execute(sql, params)
            for row in cursor.fetchall():
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    results.append(_format_file_row(row))

            if results:
                break

        # 2. If no FTS results, try SQL LIKE with clean_term
        if not results and clean_term:
            raw_like = f"%{clean_term.strip()}%"
            sql_fallback = """
                SELECT id, filepath, filename, extension, parent_dir, size_bytes, mtime
                FROM file_records
                WHERE filename LIKE ? OR filepath LIKE ?
            """
            params = [raw_like, raw_like]
            if effective_ext:
                norm_ext = f".{effective_ext.lstrip('.')}".lower()
                sql_fallback += " AND extension = ?"
                params.append(norm_ext)

            sql_fallback += " ORDER BY mtime DESC LIMIT ?"
            params.append(limit)

            cursor.execute(sql_fallback, params)
            for row in cursor.fetchall():
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    results.append(_format_file_row(row))

        # 3. If still no results, fallback to raw query LIKE
        if not results and query.strip():
            raw_like = f"%{query.strip()}%"
            sql_fallback = """
                SELECT id, filepath, filename, extension, parent_dir, size_bytes, mtime
                FROM file_records
                WHERE filename LIKE ? OR filepath LIKE ?
            """
            params = [raw_like, raw_like]
            if effective_ext:
                norm_ext = f".{effective_ext.lstrip('.')}".lower()
                sql_fallback += " AND extension = ?"
                params.append(norm_ext)

            sql_fallback += " ORDER BY mtime DESC LIMIT ?"
            params.append(limit)

            cursor.execute(sql_fallback, params)
            for row in cursor.fetchall():
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    results.append(_format_file_row(row))

    except Exception as e:
        logger.error(f"FTS search error: {e}")
    finally:
        conn.close()

    return results


def _format_file_row(row: sqlite3.Row) -> Dict[str, Any]:
    """Helper to format a database row into a clean dictionary."""
    size_bytes = row["size_bytes"]
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

    mtime_dt = datetime.fromtimestamp(row["mtime"])
    return {
        "filepath": row["filepath"],
        "filename": row["filename"],
        "extension": row["extension"],
        "parent_dir": row["parent_dir"],
        "size_bytes": size_bytes,
        "size_human": size_str,
        "mtime": row["mtime"],
        "modified_at": mtime_dt.strftime("%Y-%m-%d %H:%M"),
        "exists": os.path.exists(row["filepath"])
    }


# ==============================================================================
# Tier 2: On-Demand File Inspection & Question Answering
# ==============================================================================

def inspect_and_answer_local(
    query: str,
    candidate_paths: Optional[List[str | Path]] = None,
    max_files: int = 3
) -> Dict[str, Any]:
    """
    Tier 2 On-Demand Inspection:
    1. If candidate_paths not provided, runs Tier 1 fast filter to find candidates.
    2. Opens and reads candidate files live from disk.
    3. Feeds content into AI (Local Qwen or Gemini) to answer user's question directly.
    4. Cites the exact local file paths.
    """
    if not candidate_paths:
        # Run Tier 1 to find candidates based on keywords in query
        matched = search_local_files(query, limit=max_files)
        candidate_paths = [m["filepath"] for m in matched if m["exists"]]

    if not candidate_paths:
        return {
            "answer": f"I couldn't find any relevant local files matching: '{query}'.",
            "sources": [],
            "files_inspected": 0
        }

    inspected_docs = []
    sources = []

    for path_item in candidate_paths[:max_files]:
        p = Path(path_item)
        if not p.exists() or not p.is_file():
            continue

        ext = p.suffix.lower()
        content_preview = ""

        try:
            # Route 1: Pure text / markdown / code / csv
            if ext in {".txt", ".md", ".json", ".csv", ".py", ".html", ".log", ".yaml", ".yml"}:
                content_preview = p.read_text(encoding="utf-8", errors="ignore")[:25000]

            # Route 2: Multimodal (PDF, Audio, Image)
            else:
                ai_doc = process_thought(media_path=str(p))
                content_preview = ai_doc.get("content", "")

            if content_preview.strip():
                inspected_docs.append(f"--- File: {p.name} (Path: {p}) ---\n{content_preview.strip()}\n")
                sources.append({
                    "filename": p.name,
                    "filepath": str(p),
                    "extension": ext,
                    "snippet": content_preview[:200] + ("..." if len(content_preview) > 200 else "")
                })

        except Exception as e:
            logger.warning(f"Error inspecting local file {p}: {e}")

    if not inspected_docs:
        return {
            "answer": f"I found the files, but could not extract readable content from them.",
            "sources": sources,
            "files_inspected": len(sources)
        }

    # Synthesize answer using AI
    combined_context = "\n\n".join(inspected_docs)
    prompt = f"""
    You are an intelligent local file search assistant with direct access to documents on the user's computer.
    
    User Question: {query}
    
    Retrieved File Contents:
    {combined_context}
    
    INSTRUCTIONS:
    1. Answer the user's question directly based on the file contents above.
    2. Explicitly cite the filename and local path where you found the answer.
    3. If the answer is not contained in the files, clearly state what information is available.
    """

    answer_text = ""
    if USE_LOCAL_LLM:
        try:
            answer_text = query_local_llm(prompt, system_prompt="You are a personal file retrieval assistant.")
        except Exception:
            answer_text = ""

    if not answer_text:
        try:
            response = llm.invoke(prompt)
            content_val = response.content
            if isinstance(content_val, list):
                if content_val and isinstance(content_val[0], dict) and "text" in content_val[0]:
                    answer_text = content_val[0]["text"]
                else:
                    answer_text = str(content_val[0])
            elif isinstance(content_val, dict) and "text" in content_val:
                answer_text = content_val["text"]
            else:
                answer_text = str(content_val)
        except Exception as e:
            answer_text = f"Here is the content found in your local files:\n\n{combined_context[:500]}..."

    return {
        "answer": answer_text.strip(),
        "sources": sources,
        "files_inspected": len(inspected_docs)
    }
