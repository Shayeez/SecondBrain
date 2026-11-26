import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load variables from the .env file in the root directory
load_dotenv()

# Server Settings & API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8020"))
BRAIN_AUTH_TOKEN = os.getenv("BRAIN_AUTH_TOKEN", "").strip()

# Auto-Login (Single-User Convenience Mode)
AUTO_LOGIN_ENABLED = os.getenv("AUTO_LOGIN_ENABLED", "false").lower() in ("true", "1", "yes")
AUTO_LOGIN_USER = os.getenv("AUTO_LOGIN_USER", "").strip()


if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing from .env file!")

# Local LLM Settings (VPS or local Ollama)
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:1.5b")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "ollama")
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "true").lower() in ("true", "1", "yes")

# ChromaDB Server Settings (Optional Client/Server mode for multi-worker / multi-instance setups)
CHROMA_SERVER_HOST = os.getenv("CHROMA_SERVER_HOST", "").strip() or None
CHROMA_SERVER_PORT = int(os.getenv("CHROMA_SERVER_PORT", "8000")) if os.getenv("CHROMA_SERVER_PORT") else 8000


# Project Root Directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Cross-platform path resolution helper
def _resolve_cross_platform_path(raw_path_str: str, default_fallback: Optional[Path] = None) -> Path:
    """Translates paths across macOS, Linux, WSL, and Windows.
    - Expands user home directory (~) and environment variables ($HOME, ${VAR})
    - Translates Windows drive paths (e.g. G:/...) to /mnt/g/... on WSL/Linux if mounted,
      or to /Volumes/... on macOS if mounted.
    - Falls back to default_fallback or PROJECT_ROOT/storage if drive does not exist.
    """
    fallback_path = default_fallback or (PROJECT_ROOT / "storage")
    if not raw_path_str or not str(raw_path_str).strip():
        return fallback_path

    path_str = os.path.expandvars(str(raw_path_str).strip())
    path_str = os.path.expanduser(path_str)

    # Check for Windows drive syntax on POSIX systems (Linux/macOS)
    if os.name != "nt" and len(path_str) > 2 and path_str[1] == ":":
        drive = path_str[0].lower()
        rest = path_str[2:].replace("\\", "/").lstrip("/")

        # 1. Linux/WSL mount (/mnt/<drive>)
        wsl_mount = Path(f"/mnt/{drive}")
        if wsl_mount.exists():
            return wsl_mount / rest

        # 2. macOS Volumes (/Volumes/<VolumeName>)
        mac_vol = Path("/Volumes")
        if mac_vol.exists():
            for v in mac_vol.iterdir():
                cand = v / rest
                if cand.exists():
                    return cand

        # 3. macOS Google Drive CloudStorage default
        mac_cloud = Path.home() / "Library" / "CloudStorage"
        if mac_cloud.exists():
            for gdir in mac_cloud.glob("GoogleDrive*"):
                cand = gdir / "My Drive" / rest
                if cand.exists():
                    return cand
                cand2 = gdir / rest
                if cand2.exists():
                    return cand2

        # Unmounted or unreachable drive on this machine: fall back safely
        return fallback_path

    try:
        return Path(path_str).resolve()
    except Exception:
        return fallback_path


# --- Primary Storage Configuration ---
# 1. Base root storage directory (configured via STORAGE_BASE_DIR or SECOND_BRAIN_STORAGE)
_raw_base = os.getenv("STORAGE_BASE_DIR") or os.getenv("SECOND_BRAIN_STORAGE")
if _raw_base:
    STORAGE_BASE_DIR = _resolve_cross_platform_path(_raw_base, default_fallback=PROJECT_ROOT / "storage")
else:
    # Backward compatibility: check legacy STORAGE_DIR
    _legacy_storage = os.getenv("STORAGE_DIR", "")
    if _legacy_storage:
        _resolved_legacy = _resolve_cross_platform_path(_legacy_storage, default_fallback=PROJECT_ROOT / "storage")
        # If legacy STORAGE_DIR pointed to Raw_Inbox, extract its parent as the base
        if _resolved_legacy.name.lower() in ("raw_inbox", "rawinbox"):
            STORAGE_BASE_DIR = _resolved_legacy.parent
        else:
            STORAGE_BASE_DIR = _resolved_legacy
    else:
        STORAGE_BASE_DIR = PROJECT_ROOT / "storage"

# 2. Subfolders cleanly derived from STORAGE_BASE_DIR (or individually overridden)
STORAGE_DIR = _resolve_cross_platform_path(
    os.getenv("STORAGE_RAW_DIR", ""),
    default_fallback=STORAGE_BASE_DIR / "Raw_Inbox"
)
WIKI_DIR = _resolve_cross_platform_path(
    os.getenv("STORAGE_WIKI_DIR", ""),
    default_fallback=STORAGE_BASE_DIR / "Processed_Wiki"
)
USERS_STORAGE_DIR = _resolve_cross_platform_path(
    os.getenv("USERS_STORAGE_DIR", ""),
    default_fallback=STORAGE_BASE_DIR / "users"
)

# 3. Vector Database Directory (ChromaDB)
# Ideal place is local fast SSD/NVMe disk, separate from cloud sync folders
_raw_chroma = os.getenv("CHROMA_DIR", "")
if _raw_chroma:
    CHROMA_DIR = _resolve_cross_platform_path(_raw_chroma, default_fallback=PROJECT_ROOT / "chroma_db")
else:
    CHROMA_DIR = PROJECT_ROOT / "chroma_db"

# 4. Multi-User Registry File
USERS_DATA_FILE = _resolve_cross_platform_path(
    os.getenv("USERS_DATA_FILE", ""),
    default_fallback=PROJECT_ROOT / "users.json"
)

# --- 5. Cross-Platform Local Machine File Search Settings ---
# Comma-separated list of directories to scan for fast local search
# e.g., LOCAL_SEARCH_DIRS="~/Documents,~/Downloads,~/Projects"
_raw_search_dirs = os.getenv("LOCAL_SEARCH_DIRS", "").strip()
if _raw_search_dirs:
    LOCAL_SEARCH_DIRS = [
        _resolve_cross_platform_path(d.strip())
        for d in _raw_search_dirs.split(",")
        if d.strip()
    ]
else:
    # Default sensible user folders for Mac, Linux, and Windows
    LOCAL_SEARCH_DIRS = [
        d for d in [
            Path.home() / "Documents",
            Path.home() / "Downloads",
            Path.home() / "Desktop"
        ] if d.exists()
    ]

# Local SQLite FTS5 File Index Database Path
_raw_index_db = os.getenv("LOCAL_INDEX_DB_PATH", "").strip()
if _raw_index_db:
    LOCAL_INDEX_DB_PATH = _resolve_cross_platform_path(_raw_index_db, default_fallback=STORAGE_BASE_DIR / "file_index.sqlite3")
else:
    LOCAL_INDEX_DB_PATH = STORAGE_BASE_DIR / "file_index.sqlite3"

# Common system directories to ignore during indexing
DEFAULT_EXCLUDED_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".cache", "Library", "AppData", "$RECYCLE.BIN", "System Volume Information",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".tox", "dist", "build",
    ".gemini", ".antigravity"
}

# PARA Framework categories for structured note storage
PARA_CATEGORIES = ["Projects", "Areas", "Resources", "Archive"]

# Media subfolders for organized raw inbox storage
MEDIA_CATEGORIES = ["Images", "Audio", "Documents"]

# Safely ensure base directories exist
for target_dir in [STORAGE_BASE_DIR, STORAGE_DIR, WIKI_DIR, USERS_STORAGE_DIR, CHROMA_DIR]:
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

for category in PARA_CATEGORIES:
    try:
        (WIKI_DIR / category).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

for media_type in MEDIA_CATEGORIES:
    try:
        (STORAGE_DIR / media_type).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

