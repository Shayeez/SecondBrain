import os
from pathlib import Path
from dotenv import load_dotenv

# Load variables from the .env file in the root directory
load_dotenv()

# Server Settings & API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8020"))
BRAIN_AUTH_TOKEN = os.getenv("BRAIN_AUTH_TOKEN", "").strip()


if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing from .env file!")

# Local LLM Settings (VPS or local Ollama)
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:1.5b")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "ollama")
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "true").lower() in ("true", "1", "yes")


# Project Root Directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Storage Paths
def _resolve_cross_platform_path(raw_path_str: str) -> Path:
    """Translates Windows drive paths (e.g. G:/...) to /mnt/g/... when running on Linux/WSL.
    If the target drive device does not exist or cannot be mounted, falls back to local storage."""
    fallback_path = PROJECT_ROOT / "storage" / "Raw_Inbox"
    if not raw_path_str:
        return fallback_path
    if os.name != "nt" and len(raw_path_str) > 2 and raw_path_str[1] == ":":
        drive = raw_path_str[0].lower()
        drive_mount = Path(f"/mnt/{drive}")
        if not drive_mount.exists():
            return fallback_path
        rest = raw_path_str[2:].replace("\\", "/").lstrip("/")
        return drive_mount / rest
    return Path(raw_path_str)

STORAGE_DIR = _resolve_cross_platform_path(os.getenv("STORAGE_DIR", "C:/SecondBrain/Raw_Inbox"))
WIKI_DIR = STORAGE_DIR.parent / "Processed_Wiki"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(PROJECT_ROOT / "chroma_db")))

# Multi-User Storage & Accounts
USERS_DATA_FILE = PROJECT_ROOT / "users.json"
USERS_STORAGE_DIR = STORAGE_DIR.parent / "users"

# PARA Framework categories for structured note storage
PARA_CATEGORIES = ["Projects", "Areas", "Resources", "Archive"]

# Media subfolders for organized raw inbox storage
MEDIA_CATEGORIES = ["Images", "Audio", "Documents"]

# Ensure directories exist with fallback for headless Linux
try:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    USERS_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    for category in PARA_CATEGORIES:
        (WIKI_DIR / category).mkdir(parents=True, exist_ok=True)
    for media_type in MEDIA_CATEGORIES:
        (STORAGE_DIR / media_type).mkdir(parents=True, exist_ok=True)
except OSError:
    STORAGE_DIR = PROJECT_ROOT / "storage" / "Raw_Inbox"
    WIKI_DIR = PROJECT_ROOT / "storage" / "Processed_Wiki"
    USERS_STORAGE_DIR = PROJECT_ROOT / "storage" / "users"
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    USERS_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    for category in PARA_CATEGORIES:
        (WIKI_DIR / category).mkdir(parents=True, exist_ok=True)
    for media_type in MEDIA_CATEGORIES:
        (STORAGE_DIR / media_type).mkdir(parents=True, exist_ok=True)
