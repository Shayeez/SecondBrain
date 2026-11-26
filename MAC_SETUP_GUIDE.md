# Second Brain: macOS Local Setup & Packaging Guide

This guide explains how to package, configure, and operate the **Second Brain** knowledge engine locally on macOS (supporting both **Apple Silicon M1/M2/M3/M4** and **Intel Macs**).

---

## 1. Key macOS Architectural Advantages

- **Apple Silicon Metal Acceleration:** Ollama runs `qwen2.5:1.5b` (or `qwen2.5:7b`) directly on Apple Silicon Unified Memory using Apple's **Metal Performance Shaders (MPS)**. Inference takes ~200–500ms with 0 cloud token cost.
- **Native Safari / iOS PWA:** Add to Dock / Home Screen as a standalone desktop app.
- **Local APFS Performance:** ChromaDB's SQLite database and HNSW vector index run at maximum speed on Apple's APFS SSD with sub-10ms search latency.

---

## 2. Quick Start: One-Click Setup

### Step 1: Run the macOS Setup Script
```bash
cd /path/to/project-secondbrain
chmod +x setup_mac.sh run_mac.sh
./setup_mac.sh
```

The script automatically:
1. Detects Apple Silicon vs. Intel architecture.
2. Verifies Xcode Command Line Tools (`xcode-select`) for native C++ ChromaDB bindings.
3. Checks/installs Python 3.10+ and Ollama via Homebrew.
4. Creates a Python virtual environment (`.venv`) and installs all package dependencies.
5. Pulls `qwen2.5:1.5b` into Ollama.
6. Generates your `.env` configuration.

### Step 2: Configure `.env`
Edit your `.env` file to insert your Gemini API Key:
```bash
nano .env
```
Ensure:
```ini
GEMINI_API_KEY="your-gemini-api-key"
STORAGE_BASE_DIR="~/SecondBrain"
CHROMA_DIR="./chroma_db"
```

### Step 3: Launch Second Brain
```bash
./run_mac.sh
```
Open **[http://localhost:8020](http://localhost:8020)** in Safari or Chrome.

---

## 3. Storage Architecture: Folder Configuration

All storage locations are controlled via environment variables:

| Environment Variable | Recommended macOS Value | Purpose |
| :--- | :--- | :--- |
| `STORAGE_BASE_DIR` | `~/SecondBrain` or `~/Library/CloudStorage/GoogleDrive-.../My Drive/SecondBrain` | Primary root storage directory for all vaults, notes, and media. |
| `CHROMA_DIR` | `./chroma_db` or `~/Library/Application Support/SecondBrain/chroma_db` | **Local SSD only.** Must NOT be placed inside Google Drive or iCloud sync. |
| `USERS_DATA_FILE` | `~/SecondBrain/users.json` | Path to multi-user registry and storage quotas. |
| `STORAGE_RAW_DIR` | *(Derived: `STORAGE_BASE_DIR/Raw_Inbox`)* | Optional override for raw media folder. |
| `STORAGE_WIKI_DIR`| *(Derived: `STORAGE_BASE_DIR/Processed_Wiki`)*| Optional override for processed Markdown notes. |
| `USERS_STORAGE_DIR`| *(Derived: `STORAGE_BASE_DIR/users`)* | Root folder holding isolated user subfolders. |

### Using Google Drive on macOS
If you use Google Drive for Desktop on Mac, set:
```ini
STORAGE_BASE_DIR="~/Library/CloudStorage/GoogleDrive-your_email@gmail.com/My Drive/SecondBrain"
CHROMA_DIR="./chroma_db"
```
* **Why this split works:** Your Markdown notes and media sync across your phone, tablet, and Google Drive cloud, while your ChromaDB index stays safely on your local fast APFS drive (avoiding SQLite write-lock corruption).

---

## 4. Multi-User Isolation on macOS

Multi-user management functions identically to the server:
- User accounts are defined in `users.json`.
- Each user has their own physical directory under `STORAGE_BASE_DIR/users/<username>/`:
  - `Raw_Inbox/` (Audio, Images, PDFs)
  - `Processed_Wiki/` (Projects, Areas, Resources, Archive)
- ChromaDB automatically partitions vectors into isolated collections: `vault_<username>`.
- Cross-tenant queries are blocked at both the file system and vector database levels.

---

## 5. Running 24/7 as a Background Daemon on macOS (`launchd`)

macOS uses **`launchd`** instead of Linux `systemd`. To run Second Brain continuously in the background and start automatically on Mac login:

### Step 1: Customize the Plist Template
Open `deploy/com.secondbrain.server.plist` and update the paths to match your Mac username and repository location:
```bash
sed -i '' "s|/Users/REPLACE_WITH_USERNAME|${HOME}|g" deploy/com.secondbrain.server.plist
```

### Step 2: Install to LaunchAgents
```bash
cp deploy/com.secondbrain.server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.secondbrain.server.plist
```

### Step 3: Managing the Daemon
- **Check Status / Logs:**
  ```bash
  tail -f ~/Library/Logs/SecondBrain.log
  tail -f ~/Library/Logs/SecondBrain.err.log
  ```
- **Stop Daemon:**
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.secondbrain.server.plist
  ```
- **Restart Daemon:**
  ```bash
  launchctl unload ~/Library/LaunchAgents/com.secondbrain.server.plist
  launchctl load ~/Library/LaunchAgents/com.secondbrain.server.plist
  ```

---

## 6. macOS Browser Permissions (Microphone & Audio)

To record voice memos directly from Safari or Chrome on macOS:
1. Open **System Settings > Privacy & Security > Microphone**.
2. Ensure Safari / Google Chrome is toggled **ON**.
3. In browser, navigate to `http://localhost:8020`. When prompted, click **"Allow Microphone Access"**.
4. *(Note: Browsers only permit microphone capture over a Secure Context: `localhost`, `127.0.0.1`, or `https://`).*

---

## 7. Zero-Click Auto-Login (Single-User Personal Mac)

If Second Brain is running on your personal, password-protected Mac, typing the vault token every time can be bypassed for zero-click instant access:

1. In `.env`, set:
   ```ini
   AUTO_LOGIN_ENABLED="true"
   AUTO_LOGIN_USER="shayeez"  # (Or any username in users.json)
   ```
2. Open `http://localhost:8020`. The vault opens immediately without any password prompt or clicks.
3. *(To restore strict password gating when sharing your machine or deploying to a server, set `AUTO_LOGIN_ENABLED="false"`).*

---

## 8. Batch Ingestion CLI on macOS (`brain-import`)

You can ingest entire folders of documents, PDFs, voice recordings, and notes from your Mac terminal:

```bash
# Preview what would be processed without changing files or spending API tokens:
./.venv/bin/brain-import ~/Documents/Archive --dry-run

# Ingest and safely copy files into the Brain's vault:
./.venv/bin/brain-import ~/Documents/MeetingNotes --mode copy

# Ingest without duplicating disk space (Move / Cut & Paste):
./.venv/bin/brain-import ~/Downloads/PDFs --mode move

# Ingest in-place (records paths to original files, 0 extra disk bytes):
./.venv/bin/brain-import ~/Music/VoiceMemos --mode reference
```

### Ingestion Workflow:
1. **Deduplication:** Computes SHA-256 hash of each file and skips duplicates already in ChromaDB.
2. **AI Processing:** Uses local Ollama (`qwen2.5:1.5b`) on Apple Silicon GPU for text files (0 token cost) and Gemini Flash for PDFs/Audio.
3. **Dual-Write:** Creates formatted `.md` wiki notes under `~/SecondBrain/users/<user>/Processed_Wiki/` and indexes vector embeddings into ChromaDB.

---

## 9. Local Mac File Search & On-Demand AI Inspection

Second Brain provides cross-platform file searching that indexes files on your Mac in milliseconds and lets you interrogate them directly from the web deck or terminal:

### In Terminal:
```bash
# 1. Index your Documents, Downloads, and Desktop (~10,000 files in ~1 second):
./.venv/bin/brain-scan

# 2. Search for files:
./.venv/bin/brain-find "tax return" --ext .pdf

# 3. Ask questions about local files (On-demand AI inspection):
./.venv/bin/brain-find "what was the net amount in 2025 tax return?" --inspect
```

### In Web Deck:
* In the input box, type: `/find lease agreement` to get a list of matching file paths.
* Type: `/find lease agreement what is the monthly rent?` to have the AI open and read the candidate document live to answer your question!
