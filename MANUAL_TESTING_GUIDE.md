# Second Brain — Step-by-Step Manual Testing Guide

**Document Purpose:** A hands-on, human-friendly testing manual. Follow these steps one-by-one to test and verify every feature of your Second Brain system on WSL and your Windows browser.

---

## 📋 Pre-Test Setup (5-Minute Prep)

Before starting the manual tests, prepare a clean test environment:

### Step 1: Wipe Previous Test Clutter (Start Fresh)
In your WSL terminal:
```bash
cd /home/shayeez/projects/project-secondbrain
./.venv/bin/python clean_vault.py --confirm
```
*Expected Result:* Displays `Vault for 'shayeez' is now clean and empty! Ready for real personal notes.`

### Step 2: (Optional) Start the VPS SSH Tunnel
If you want to use the free VPS Qwen model (`qwen2.5:1.5b`):
```bash
./tunnel_vps.sh start
./tunnel_vps.sh status
```
*Expected Result:* Displays `✅ VPS SSH Tunnel is ACTIVE and responding on http://127.0.0.1:11434`.

### Step 3: Launch Second Brain
```bash
./run_wsl.sh
```
*Expected Result:* Terminal displays:
```text
🚀 Starting Second Brain Web Server on port 8020...
🌐 Open in Windows browser (Chrome / Edge / Brave):
   👉 http://localhost:8020
```

---

## 🧪 Test Track 1: Authentication & Zero-Click Auto-Login

---

### Test Case 1.1: Zero-Click Auto-Login Verification
* **Objective:** Verify that opening the Web Deck automatically logs you into Shayeez's vault without asking for a password when auto-login is enabled.
* **Method:** Windows Browser
* **Pre-conditions:** `AUTO_LOGIN_ENABLED="true"` in `.env`. Server running on port 8020.
* **Action Steps:**
  1. Open Chrome or Edge in Windows.
  2. Navigate to: `http://localhost:8020`
* **Expected Result:**
  - The login modal does **NOT** appear (or vanishes immediately).
  - The main dashboard appears showing the top bar with **Shayeez (10 GB)**.
  - The stat counters show `0` (Total Notes: 0, Vector Embeddings: 0) since we started fresh.
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 1.2: Lock Vault & Manual Passphrase Login
* **Objective:** Verify that you can manually lock your vault and unlock it using your secure passphrase.
* **Method:** Windows Browser
* **Pre-conditions:** Logged into dashboard.
* **Action Steps:**
  1. In the top navigation bar, click the **Lock Vault** button (padlock icon).
  2. Notice the **Second Brain Vault** login card appears.
  3. In the **User Access Token / Passphrase** input, enter:
     ```text
     shayeez-vault-2026
     ```
  4. Click the **eye icon** to toggle password visibility (verify you can see and hide text).
  5. Click **Unlock Vault $\rightarrow$**.
* **Expected Result:**
  - A green toast notification appears: `✓ Vault Unlocked Successfully`.
  - The login overlay disappears and your dashboard re-opens.
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 1.3: Invalid Passphrase Rejection
* **Objective:** Verify that entering an incorrect passphrase blocks access and shows an error banner.
* **Method:** Windows Browser
* **Pre-conditions:** Vault is locked (showing login modal).
* **Action Steps:**
  1. Click **Lock Vault** to return to the lock screen.
  2. In the passphrase box, enter:
     ```text
     wrong-passphrase-123
     ```
  3. Click **Unlock Vault $\rightarrow$**.
* **Expected Result:**
  - The modal stays on screen.
  - A red error banner appears: `⚠️ Invalid access key or passphrase.`
  - The dashboard is not accessible.
* **Status:** `[ ] PASS   [ ] FAIL`

---

## 🧪 Test Track 2: Quick Capture & P.A.R.A Categorization

---

### Test Case 2.1: Project Note Capture (Automatic Classification)
* **Objective:** Verify capturing a time-bound project note automatically categorizes it into **Projects**.
* **Method:** Windows Browser
* **Pre-conditions:** Logged into `http://localhost:8020`.
* **Action Steps:**
  1. In the **Quick Capture** text area on the dashboard, paste:
     ```text
     Project Odyssey: Build and ship the mobile beta app by December 15. Key deliverables include OAuth login and push notifications.
     ```
  2. Click **Capture Note**.
* **Expected Result:**
  - A green success toast appears: `✓ Note Captured & Processed`.
  - The **Total Notes** counter increments from `0` to `1`.
  - In the **Vault Explorer** below, the note appears with a **Projects** badge.
  - Click on the note card: A preview modal opens showing formatted Markdown, frontmatter metadata, and tags (`#project-odyssey`, `#mobile-beta`).
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 2.2: Area of Responsibility Capture
* **Objective:** Verify capturing an ongoing responsibility automatically routes to **Areas**.
* **Method:** Windows Browser
* **Pre-conditions:** Logged into `http://localhost:8020`.
* **Action Steps:**
  1. In the Quick Capture box, enter:
     ```text
     Personal Health Routine: Daily morning stretching, 3x weekly gym sessions, and track resting heart rate every Sunday.
     ```
  2. Click **Capture Note**.
* **Expected Result:**
  - The note is saved and appears in the Vault Explorer.
  - The badge displays **Areas** (or clicking the "Areas" category tab filters specifically to this note).
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 2.3: SHA-256 Duplicate Suppression
* **Objective:** Verify that entering the identical content twice does not create duplicate clutter.
* **Method:** Windows Browser
* **Pre-conditions:** Test Case 2.2 completed.
* **Action Steps:**
  1. Paste the **exact same text** from Test Case 2.2 again into the Quick Capture box:
     ```text
     Personal Health Routine: Daily morning stretching, 3x weekly gym sessions, and track resting heart rate every Sunday.
     ```
  2. Click **Capture Note**.
* **Expected Result:**
  - An informational toast appears: `ℹ️ Duplicate Note: Content already exists in vault.`
  - The **Total Notes** counter stays at `2` (does not increment to 3).
  - No duplicate file is created.
* **Status:** `[ ] PASS   [ ] FAIL`

---

## 🧪 Test Track 3: Local Machine File Search & Inspection (Tier 1 & Tier 2)

---

### Test Case 3.1: Index Local Machine Files (`brain-scan`)
* **Objective:** Index local machine directories into the SQLite FTS5 database.
* **Method:** WSL Terminal
* **Pre-conditions:** Open a second WSL terminal tab.
* **Action Steps:**
  1. In your terminal, run:
     ```bash
     cd /home/shayeez/projects/project-secondbrain
     ./.venv/bin/brain-scan
     ```
* **Expected Result:**
  - Terminal displays:
    ```text
    🧠 Scanning configured directories into Local SQLite FTS5 Index...
    ✓ Scanned: ... | Inserted: ... | Updated: ... | Errors: 0
    ✨ Indexing complete in 0.X seconds.
    ```
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 3.2: Instant Terminal Search (`brain-find`)
* **Objective:** Verify sub-5ms keyword search across filenames and paths.
* **Method:** WSL Terminal
* **Action Steps:**
  1. In terminal, search for any document or project file on your machine:
     ```bash
     ./.venv/bin/brain-find "test"
     ```
  2. Search filtering by file extension:
     ```bash
     ./.venv/bin/brain-find "py" --ext py --limit 5
     ```
* **Expected Result:**
  - Instantly outputs a structured table containing matching files, absolute paths, file sizes, and modification timestamps.
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 3.3: Web Deck `/find` Shortcut
* **Objective:** Locate local machine files directly inside the browser Web Deck.
* **Method:** Windows Browser
* **Pre-conditions:** Logged into `http://localhost:8020`.
* **Action Steps:**
  1. In the Web Deck **Quick Capture** box, type:
     ```text
     /find test
     ```
  2. Press Enter or click **Capture Note**.
* **Expected Result:**
  - A specialized **Local File Search Results** card appears in the UI.
  - Lists the matching local files with path icons and file sizes.
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 3.4: Tier 2 On-Demand Deep AI Inspection
* **Objective:** Ask a natural question about candidate local files without importing them into ChromaDB.
* **Method:** WSL Terminal or Web Deck
* **Action Steps (Terminal):**
  1. Run:
     ```bash
     ./.venv/bin/brain-find "what features are in pyproject.toml?" --inspect
     ```
* **Expected Result:**
  - Terminal reads `pyproject.toml` live from disk, passes it to the AI, and outputs a synthesized summary citing `file:///home/shayeez/projects/project-secondbrain/pyproject.toml`.
* **Status:** `[ ] PASS   [ ] FAIL`

---

## 🧪 Test Track 4: Batch Folder Ingestion CLI (`brain-import`)

---

### Test Case 4.1: Dry-Run Batch Simulation
* **Objective:** Test scanning a folder without writing any files to disk.
* **Method:** WSL Terminal
* **Action Steps:**
  1. Create a temporary folder with 2 test files:
     ```bash
     mkdir -p /tmp/sb_manual_test
     echo "# Cloud Architecture Migration Plan\nMigrate cluster to Kubernetes by Q3." > /tmp/sb_manual_test/cloud_plan.md
     echo "Meeting Notes: Budget discussion with team." > /tmp/sb_manual_test/notes.txt
     ```
  2. Run batch import in **Dry-Run** mode:
     ```bash
     ./.venv/bin/brain-import /tmp/sb_manual_test --dry-run
     ```
* **Expected Result:**
  - Console prints: `🧪 Dry Run: YES (Simulation only - no notes will be created)`
  - Lists the 2 candidate files.
  - Summary shows `✓ Ingested: 0 | Skipped: 0 | Failed: 0`.
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 4.2: Live Batch Ingestion into Vault
* **Objective:** Batch-import files into Shayeez's vault and index them into ChromaDB.
* **Method:** WSL Terminal
* **Action Steps:**
  1. Run live batch import:
     ```bash
     ./.venv/bin/brain-import /tmp/sb_manual_test --user shayeez --copy
     ```
* **Expected Result:**
  - Each file is processed and categorized:
    - `[1/2] Processing: cloud_plan.md ... ✓ [Projects]`
    - `[2/2] Processing: notes.txt ... ✓ [Areas]`
  - Summary shows: `✓ Ingested: 2 | Skipped: 0 | Failed: 0`.
  - In your browser at `http://localhost:8020`, refresh: The **Total Notes** counter increments by 2, and both imported notes appear in your Vault Explorer.
* **Status:** `[ ] PASS   [ ] FAIL`

---

### Test Case 4.3: Batch Duplicate Suppression
* **Objective:** Re-run batch import on the same folder to verify automatic duplicate skipping.
* **Method:** WSL Terminal
* **Action Steps:**
  1. Run the exact same batch command again:
     ```bash
     ./.venv/bin/brain-import /tmp/sb_manual_test --user shayeez --copy
     ```
* **Expected Result:**
  - Summary shows: `✓ Ingested: 0 | ⏭️ Skipped: 2 (Duplicates / Filtered) | Failed: 0`.
  - No duplicate files are added to the vault.
* **Status:** `[ ] PASS   [ ] FAIL`

---

## 🧪 Test Track 5: Conversational Semantic RAG (`/ask`)

---

### Test Case 5.1: Conversational Q&A with Context Retrieval
* **Objective:** Ask a question about your knowledge vault and verify the AI synthesizes an answer from your notes.
* **Method:** Windows Browser
* **Pre-conditions:** Ingested notes from Track 2 & Track 4.
* **Action Steps:**
  1. In the Web Deck search bar or chat input, ask:
     ```text
     When is the cloud architecture migration scheduled to happen?
     ```
  2. Press Enter or click **Ask Brain**.
* **Expected Result:**
  - The AI generates a synthesized response stating that the cluster migration is scheduled for **Q3**.
  - A **Sources** section appears at the bottom referencing `cloud_plan.md` in **Projects**.
* **Status:** `[ ] PASS   [ ] FAIL`

---

## 🧪 Test Track 6: Multi-Tenant Vault Isolation

---

### Test Case 6.1: Tenant Vault Privacy Barrier (Shamim vs Shayeez)
* **Objective:** Verify that another user (Shamim) cannot view or search Shayeez's private notes.
* **Method:** Windows Browser
* **Action Steps:**
  1. In the Web Deck, click **Lock Vault** (padlock icon).
  2. Authenticate as **Shamim** using her vault passphrase:
     ```text
     shamim-vault-2026
     ```
  3. Click **Unlock Vault**.
* **Expected Result:**
  - Top bar updates to display: **Shamim (10 GB)**.
  - Counter shows **Total Notes: 0**.
  - Vault Explorer is completely **empty** (none of Shayeez's notes appear).
  4. In the search box, ask:
     ```text
     When is the cloud architecture migration scheduled to happen?
     ```
  - The AI responds that **no matching information was found** in Shamim's vault.
* **Status:** `[ ] PASS   [ ] FAIL`

---

## 🧪 Test Track 7: Progressive Web App (PWA) Offline Test

---

### Test Case 7.1: Service Worker Registration & PWA Readiness
* **Objective:** Confirm PWA service worker is active and caching assets.
* **Method:** Windows Browser (Chrome / Edge)
* **Action Steps:**
  1. On `http://localhost:8020`, press **F12** to open Developer Tools.
  2. Click the **Application** tab.
  3. In the left panel, click **Service Workers**.
* **Expected Result:**
  - Status shows: `sw.js activated and is running`.
  - In the browser address bar, the **Install Second Brain** icon (desktop screen with arrow) is visible.
* **Status:** `[ ] PASS   [ ] FAIL`

---

## 📊 Manual Test Execution Summary Sheet

Print or copy this scorecard to record your results:

| Test ID | Test Name | Target Module | Result (Pass / Fail) | Notes / Observations |
| :--- | :--- | :--- | :--- | :--- |
| **TC-1.1** | Zero-Click Auto-Login | Auth | `[ ]` | |
| **TC-1.2** | Manual Passphrase Unlock | Auth | `[ ]` | |
| **TC-1.3** | Invalid Passphrase Rejection | Security | `[ ]` | |
| **TC-2.1** | Project Note Capture | P.A.R.A | `[ ]` | |
| **TC-2.2** | Area Note Capture | P.A.R.A | `[ ]` | |
| **TC-2.3** | SHA-256 Duplicate Check | Storage | `[ ]` | |
| **TC-3.1** | Index Local Files (`brain-scan`) | FTS5 Search | `[ ]` | |
| **TC-3.2** | Instant Search (`brain-find`) | FTS5 Search | `[ ]` | |
| **TC-3.3** | Web Deck `/find` Shortcut | Search | `[ ]` | |
| **TC-3.4** | Tier 2 Live AI Inspection | AI Inspection | `[ ]` | |
| **TC-4.1** | Batch Import Dry-Run | Batch CLI | `[ ]` | |
| **TC-4.2** | Batch Live Import | Batch CLI | `[ ]` | |
| **TC-4.3** | Batch Duplicate Suppression | Batch CLI | `[ ]` | |
| **TC-5.1** | Conversational Vector RAG | AI & RAG | `[ ]` | |
| **TC-6.1** | Multi-User Tenant Isolation | Multi-Tenancy | `[ ]` | |
| **TC-7.1** | PWA Service Worker Ready | Frontend PWA | `[ ]` | |

**Tester Name:** Shayeez  
**Date Executed:** ____________________  
**Final Verdict:** `[ ] APPROVED FOR DAILY USE`
