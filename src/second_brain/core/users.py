import json
import logging
import secrets
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, status

from second_brain.config import USERS_DATA_FILE, USERS_STORAGE_DIR, BRAIN_AUTH_TOKEN, PARA_CATEGORIES, MEDIA_CATEGORIES

logger = logging.getLogger("second_brain.users")

DEFAULT_USERS = {
    "shayeez": {
        "token": BRAIN_AUTH_TOKEN or "shayeez-vault-2026",
        "display_name": "Shayeez",
        "max_storage_mb": 10240,
        "created_at": "2026-10-20"
    },
    "shamim": {
        "token": "shamim-vault-2026",
        "display_name": "Shamim",
        "max_storage_mb": 10240,
        "created_at": "2026-10-20"
    },
    "shayeez_shamim": {
        "token": "shayeez-shamim-vault-2026",
        "display_name": "Shayeez & Shamim",
        "max_storage_mb": 51200,
        "created_at": "2026-10-20"
    }
}


def load_user_registry() -> dict:
    """Loads users from users.json, creating a default template if not present."""
    if not USERS_DATA_FILE.exists():
        try:
            USERS_DATA_FILE.write_text(json.dumps({"users": DEFAULT_USERS}, indent=2), encoding="utf-8")
            logger.info(f"Initialized default multi-user registry at {USERS_DATA_FILE}")
            return DEFAULT_USERS
        except Exception as e:
            logger.error(f"Failed to create default users.json: {e}")
            return DEFAULT_USERS

    try:
        data = json.loads(USERS_DATA_FILE.read_text(encoding="utf-8"))
        users = data.get("users", {})
        if not users:
            return DEFAULT_USERS
        return users
    except Exception as e:
        logger.error(f"Error reading users.json: {e}")
        return DEFAULT_USERS

def save_user_registry(users: dict):
    """Saves the user registry back to users.json."""
    try:
        USERS_DATA_FILE.write_text(json.dumps({"users": users}, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to write users.json: {e}")

def get_user_by_token(provided_token: Optional[str]) -> Optional[dict]:
    """
    Finds and authenticates a user by matching their token in constant time.
    Returns the enriched user profile with isolated storage paths.
    """
    if not provided_token:
        return None
        
    token_str = provided_token.strip()
    registry = load_user_registry()

    matched_username = None
    matched_data = None

    for uname, udata in registry.items():
        user_tok = udata.get("token", "").strip()
        if user_tok and secrets.compare_digest(token_str, user_tok):
            matched_username = uname
            matched_data = udata
            break

    # Also check if token matches legacy BRAIN_AUTH_TOKEN directly
    if not matched_data and BRAIN_AUTH_TOKEN and secrets.compare_digest(token_str, BRAIN_AUTH_TOKEN.strip()):
        matched_username = "shayeez"
        matched_data = registry.get("shayeez", DEFAULT_USERS["shayeez"])

    if not matched_data or not matched_username:
        return None

    # Construct and isolate user paths
    user_root = USERS_STORAGE_DIR / matched_username
    storage_dir = user_root / "Raw_Inbox"
    wiki_dir = user_root / "Processed_Wiki"
    collection_name = f"vault_{matched_username.replace('-', '_').lower()}"

    user_obj = {
        "username": matched_username,
        "display_name": matched_data.get("display_name", matched_username.capitalize()),
        "max_storage_mb": int(matched_data.get("max_storage_mb", 5120)),
        "user_root": user_root,
        "storage_dir": storage_dir,
        "wiki_dir": wiki_dir,
        "collection_name": collection_name
    }

    # Ensure isolated physical directories exist for this user
    ensure_user_storage(user_obj)
    return user_obj

def ensure_user_storage(user: dict):
    """Creates the user's isolated directory tree and PARA folders."""
    try:
        user_root = user["user_root"]
        storage_dir = user["storage_dir"]
        wiki_dir = user["wiki_dir"]

        user_root.mkdir(parents=True, exist_ok=True)
        storage_dir.mkdir(parents=True, exist_ok=True)
        wiki_dir.mkdir(parents=True, exist_ok=True)

        for cat in PARA_CATEGORIES:
            (wiki_dir / cat).mkdir(parents=True, exist_ok=True)

        for med in MEDIA_CATEGORIES:
            (storage_dir / med).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Error provisioning storage for {user['username']}: {e}")

def get_user_storage_metrics(user: dict) -> dict:
    """Calculates disk usage within the user's isolated directory."""
    user_root = user["user_root"]
    max_mb = user.get("max_storage_mb", 5120)

    total_bytes = 0
    file_count = 0
    if user_root.exists():
        for f in user_root.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                try:
                    total_bytes += f.stat().st_size
                    file_count += 1
                except Exception:
                    pass

    used_mb = total_bytes / (1024 * 1024)
    percent_used = (used_mb / max_mb * 100) if max_mb > 0 else 0.0

    return {
        "used_bytes": total_bytes,
        "used_mb": round(used_mb, 2),
        "max_mb": max_mb,
        "percent_used": round(min(100.0, percent_used), 1),
        "file_count": file_count
    }

def check_user_quota(user: dict, incoming_bytes: int = 0):
    """Enforces storage quota limit. Raises 413 if exceeded."""
    metrics = get_user_storage_metrics(user)
    incoming_mb = incoming_bytes / (1024 * 1024)
    if (metrics["used_mb"] + incoming_mb) > metrics["max_mb"]:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Storage quota exceeded. Your account is using {metrics['used_mb']} MB of {metrics['max_mb']} MB."
        )
