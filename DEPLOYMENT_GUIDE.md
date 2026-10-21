# Second Brain: Production Deployment & Operations Guide

This guide provides the complete, step-by-step procedure for deploying and operating Second Brain on your Ubuntu VPS (`51.81.203.132`), under user **`app_test`** in **`/home/app_test/SecondBrain`**, coexisting with other web applications, using your local VPS LLM for maximum token savings, and managing isolated multi-user vaults.

---

## 1. Architecture Summary

- **User & Path:** Runs under user `app_test` located at `/home/app_test/SecondBrain`.
- **Frontend:** Sovereign Web & Mobile PWA (FastAPI + Vanilla JS/CSS, Zero 3rd-party dependencies).
- **AI Engine (Hybrid Router):**
  - **Local VPS LLM (`qwen2.5:1.5b`):** Categorization, tagging, PARA classification, and text queries (100% free tokens, 1-second inference).
  - **Gemini Cloud (Flash):** Native multimodal extraction (voice memo transcription, whiteboard/image OCR, document/PDF comprehension).
  - **Fault Resilience:** Automatic, silent fallback to Gemini if local LLM is temporarily unreachable.
- **Multi-Tenant Physical Vaults:**
  - `/home/app_test/SecondBrain/storage/users/shayeez/` (10 GB quota)
  - `/home/app_test/SecondBrain/storage/users/shamim/` (10 GB quota)
  - `/home/app_test/SecondBrain/storage/users/shayeez_shamim/` (50 GB quota - Maximum storage)
  - ChromaDB collections: `vault_shayeez`, `vault_shamim`, `vault_shayeez_shamim`.

---

## 2. Local Machine: Preparing & Pushing to Git

### Step 2.1: Verify Tests Locally
Before pushing any code, run the multi-user and auth verification tests:
```bash
cd /home/shayeez/projects/project-secondbrain
./.venv/bin/python test_multiuser.py
./.venv/bin/python test_auth.py
```

### Step 2.2: Push Code to Your Private Git Repository
`.gitignore` automatically ensures that your private keys (`.env`), vector index (`chroma_db/`), and personal notes (`storage/`) are **never** uploaded to Git.

```bash
cd /home/shayeez/projects/project-secondbrain

# Initialize branch and stage clean code
git branch -M main
git add .
git commit -m "feat: sovereign multi-tenant second brain with vps local llm routing"

# Add your private remote (GitHub / GitLab / Gitea) and push
git remote add origin <YOUR_GIT_REPO_URL>
git push -u origin main
```

---

## 3. VPS First-Time Setup Walkthrough (`51.81.203.132`)

### Step 3.1: Switch to `app_test` User
SSH into your VPS and ensure you are working as `app_test`:
```bash
ssh app_test@51.81.203.132
# Or if logging in as root/ubuntu:
# sudo su - app_test
```

Verify your current directory is `/home/app_test`:
```bash
pwd
# Output: /home/app_test
```

### Step 3.2: Verify Local Ollama on the VPS
Ensure Ollama is running privately on `127.0.0.1:11434`:
```bash
# Verify Ollama is active
systemctl status ollama

# Pull the lightweight, ultra-fast model (if not already done)
ollama pull qwen2.5:1.5b

# Verify it is locked to localhost (NOT exposed to the internet)
ss -tulpn | grep 11434
# Output must show: 127.0.0.1:11434
```

### Step 3.3: Clone Repository under `/home/app_test/SecondBrain`
```bash
cd /home/app_test
git clone <YOUR_GIT_REPO_URL> SecondBrain
cd /home/app_test/SecondBrain
```

### Step 3.4: Create Python Virtual Environment & Install
```bash
cd /home/app_test/SecondBrain
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools
pip install -e .
```

### Step 3.5: Configure Production `.env`
Create `/home/app_test/SecondBrain/.env`:
```bash
nano /home/app_test/SecondBrain/.env
```
Paste the following production configuration:
```ini
# External Cloud AI (for Voice/Images/PDFs)
GEMINI_API_KEY="your-actual-gemini-api-key"

# Master System Token
BRAIN_AUTH_TOKEN="brain-secret-vault-key-2026"

# Local LLM (Communicates internally inside VPS loopback)
LOCAL_LLM_BASE_URL="http://127.0.0.1:11434/v1"
LOCAL_LLM_MODEL="qwen2.5:1.5b"
LOCAL_LLM_API_KEY="ollama"
USE_LOCAL_LLM="true"

# Server Port (Dedicated port 8020 so other apps on 8000/3000 are untouched)
WEB_HOST="127.0.0.1"
WEB_PORT="8020"

# Server File Storage Paths (under app_test SecondBrain)
STORAGE_DIR="/home/app_test/SecondBrain/storage/Raw_Inbox"
CHROMA_DIR="/home/app_test/SecondBrain/chroma_db"
```
Save and exit (`Ctrl + O`, `Enter`, `Ctrl + X`). Secure file permissions:
```bash
chmod 600 /home/app_test/SecondBrain/.env
```

---

## 4. Multi-User Vault Configuration on VPS

Your user vaults are pre-defined in `/home/app_test/SecondBrain/users.json`:
```json
{
  "users": {
    "shayeez": {
      "token": "shayeez-vault-2026",
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
}
```
> **Tip:** You can change vault tokens anytime by editing `users.json`. Changes take effect instantly without restarting.

---

## 5. Setup Systemd Service (24/7 Background Run)

The service file in `deploy/second-brain.service` is pre-configured to run as user **`app_test`** in **`/home/app_test/SecondBrain`**.

1. Copy the service definition to systemd (requires sudo):
   ```bash
   sudo cp /home/app_test/SecondBrain/deploy/second-brain.service /etc/systemd/system/
   ```
2. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now second-brain
   ```
3. Verify service status:
   ```bash
   sudo systemctl status second-brain
   ```
   *(You should see `Active: active (running)` on port 8020)*.

---

## 6. Configure Nginx — Subpath on 24x7care.org

Second Brain is served at **`https://24x7care.org/secondbrain`** by adding a `location` block inside your **existing** `24x7care.org` Nginx config. No new SSL certificate is needed — it inherits the existing one.

1. Find your existing 24x7care.org Nginx server config:
   ```bash
   ls /etc/nginx/sites-available/
   # Usually: 24x7care.org  OR  default  OR  24x7care
   sudo nano /etc/nginx/sites-available/24x7care.org
   ```
2. Inside the **existing** `server { listen 443 ssl ... }` block, paste the following location blocks:
   ```nginx
   # --- Second Brain at /secondbrain ---
   location /secondbrain/ {
       proxy_pass http://127.0.0.1:8020/;   # trailing / strips /secondbrain prefix
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       client_max_body_size 100M;
       proxy_read_timeout 300s;
       proxy_connect_timeout 75s;
       proxy_send_timeout 300s;
   }

   # Redirect bare /secondbrain → /secondbrain/
   location = /secondbrain {
       return 301 $scheme://$host/secondbrain/;
   }
   ```
3. Test and reload:
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```
4. Access your app at: **`https://24x7care.org/secondbrain`**

> **No new SSL cert required.** The existing `24x7care.org` certificate already covers this path.
> The `nginx.conf` file in `deploy/nginx.conf` contains the exact snippet to paste with detailed instructions.

---

## 7. How to Apply Future Releases & Updates

Whenever you make improvements or fix code on your local computer, deploying updates takes just **two commands**:

### On Your Local Computer:
```bash
git add .
git commit -m "feat: new feature description"
git push origin main
```

### On Your VPS (as `app_test`):
```bash
cd /home/app_test/SecondBrain
git pull
sudo systemctl restart second-brain
```

### Why this update process is 100% safe:
- **No Note Overwriting:** All markdown notes, media files, and ChromaDB embeddings are stored in `/home/app_test/SecondBrain/storage/` and `chroma_db/`, which are git-ignored.
- **No Token Leakage:** The `.env` file is never touched or overwritten by Git.
- **Instant Reload:** `systemctl restart second-brain` applies code changes in under 1 second.
