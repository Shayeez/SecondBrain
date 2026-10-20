/**
 * Second Brain - In-House Web Frontend
 * Multimodal input, voice recording, RAG interaction, and PARA vault exploration.
 */

document.addEventListener("DOMContentLoaded", () => {
    // State variables
    let currentMode = "auto";
    let activeAttachedFile = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let recordingInterval = null;
    let recordingSeconds = 0;
    let cachedNotes = [];
    let activeCategoryFilter = "";

    // DOM Elements
    const captureForm = document.getElementById("captureForm");
    const thoughtInput = document.getElementById("thoughtInput");
    const btnSubmit = document.getElementById("btnSubmit");
    const fileInput = document.getElementById("fileInput");
    const modeTabs = document.querySelectorAll(".mode-tab");
    const interactionFeed = document.getElementById("interactionFeed");
    const dropOverlay = document.getElementById("dropOverlay");

    // Attachment Preview Elements
    const attachmentStrip = document.getElementById("attachmentStrip");
    const previewMediaContainer = document.getElementById("previewMediaContainer");
    const previewFilename = document.getElementById("previewFilename");
    const previewMeta = document.getElementById("previewMeta");
    const btnRemoveAttachment = document.getElementById("btnRemoveAttachment");

    // Voice Recorder Elements
    const btnMicRecord = document.getElementById("btnMicRecord");
    const voiceRecorderBar = document.getElementById("voiceRecorderBar");
    const recordingTimer = document.getElementById("recordingTimer");
    const btnCancelRecording = document.getElementById("btnCancelRecording");
    const btnStopAndSendRecording = document.getElementById("btnStopAndSendRecording");

    // Vault Explorer Elements
    const toggleExplorerBtn = document.getElementById("toggleExplorerBtn");
    const vaultDrawer = document.getElementById("vaultDrawer");
    const btnCloseDrawer = document.getElementById("btnCloseDrawer");
    const vaultSearchInput = document.getElementById("vaultSearchInput");
    const notesList = document.getElementById("notesList");
    const vaultBadge = document.getElementById("vaultBadge");
    const catPills = document.querySelectorAll(".cat-pill");

    // Header Stats
    const statTotalNotes = document.getElementById("statTotalNotes");
    const statVectorCount = document.getElementById("statVectorCount");

    // Note Modal Elements
    const noteModal = document.getElementById("noteModal");
    const modalCategoryBadge = document.getElementById("modalCategoryBadge");
    const modalTitle = document.getElementById("modalTitle");
    const modalGdrivePath = document.getElementById("modalGdrivePath");
    const modalBody = document.getElementById("modalBody");
    const modalDownloadLink = document.getElementById("modalDownloadLink");
    const btnCloseModal = document.getElementById("btnCloseModal");

    // Toast Container
    const toastContainer = document.getElementById("toastContainer");

    // Auth Gate Elements
    const authGate = document.getElementById("authGate");
    const authForm = document.getElementById("authForm");
    const authPassphrase = document.getElementById("authPassphrase");
    const btnToggleAuthVisibility = document.getElementById("btnToggleAuthVisibility");
    const rememberMe = document.getElementById("rememberMe");
    const authErrorBanner = document.getElementById("authErrorBanner");
    const authErrorMsg = document.getElementById("authErrorMsg");
    const btnLockVault = document.getElementById("btnLockVault");

    // --- Authentication State & Helpers ---
    function getAuthToken() {
        return localStorage.getItem("brain_token") || sessionStorage.getItem("brain_token") || "";
    }

    function setAuthToken(token, remember) {
        if (remember) {
            localStorage.setItem("brain_token", token);
            sessionStorage.removeItem("brain_token");
        } else {
            sessionStorage.setItem("brain_token", token);
            localStorage.removeItem("brain_token");
        }
    }

    function clearAuthToken() {
        localStorage.removeItem("brain_token");
        sessionStorage.removeItem("brain_token");
    }

    function showAuthGate(show = true) {
        if (!authGate) return;
        if (show) {
            authGate.classList.remove("hidden");
            if (authPassphrase) {
                authPassphrase.value = "";
                authPassphrase.focus();
            }
        } else {
            authGate.classList.add("hidden");
            hideAuthError();
        }
    }

    function showAuthError(msg) {
        if (authErrorBanner && authErrorMsg) {
            authErrorMsg.textContent = msg || "Invalid Access Key";
            authErrorBanner.classList.remove("hidden");
        }
    }

    function hideAuthError() {
        if (authErrorBanner) {
            authErrorBanner.classList.add("hidden");
        }
    }

    async function authFetch(url, options = {}) {
        options.headers = options.headers || {};
        const token = getAuthToken();
        if (token) {
            if (!(options.headers instanceof Headers)) {
                options.headers["Authorization"] = `Bearer ${token}`;
                options.headers["X-Brain-Token"] = token;
            } else {
                options.headers.set("Authorization", `Bearer ${token}`);
                options.headers.set("X-Brain-Token", token);
            }
        }
        
        // Ensure cookies (session token) are always sent
        if (!options.credentials) {
            options.credentials = "same-origin";
        }

        try {
            const res = await fetch(url, options);
            if (res.status === 401) {
                showAuthGate(true);
                showToast("Access token required or session expired.", "error");
            }
            return res;
        } catch (err) {
            console.error("Network error during authFetch:", err);
            throw err;
        }
    }

    // --- Markdown Parser Helper ---
    function renderMarkdown(text) {
        if (!text) return "";
        let html = text
            // Escape HTML tags to prevent XSS
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            // Code blocks
            .replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
                return `<pre class="code-block"><code>${code.trim()}</code></pre>`;
            })
            // Inline code
            .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
            // Headers
            .replace(/^### (.*$)/gim, '<h4>$1</h4>')
            .replace(/^## (.*$)/gim, '<h3>$1</h3>')
            .replace(/^# (.*$)/gim, '<h2>$1</h2>')
            // Blockquotes
            .replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>')
            // Bold & Italic
            .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            // Unordered Lists
            .replace(/^\s*[-*•]\s+(.*$)/gim, '<li>$1</li>')
            // Line breaks
            .replace(/\n\n+/g, '</p><p>')
            .replace(/\n/g, '<br>');

        return `<p>${html}</p>`.replace(/<p><\/p>/g, '');
    }

    // --- Toast Notifications ---
    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span>${type === 'success' ? '✓' : type === 'error' ? '⚠️' : 'ℹ️'}</span>
            <span>${message}</span>
        `;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(-10px)";
            setTimeout(() => toast.remove(), 250);
        }, 3500);
    }

    // --- System Stats & Notes Fetch ---
    async function loadStats() {
        try {
            const res = await authFetch("/api/stats");
            if (res.ok) {
                const data = await res.json();
                statTotalNotes.textContent = data.total_notes || 0;
                statVectorCount.textContent = data.vector_embeddings || 0;
                vaultBadge.textContent = data.total_notes || 0;

                // Render User Profile & Quota info
                if (data.user) {
                    const userNameDisplay = document.getElementById("userNameDisplay");
                    const userAvatar = document.getElementById("userAvatar");
                    const userQuotaDisplay = document.getElementById("userQuotaDisplay");

                    const name = data.user.display_name || data.user.username;
                    if (userNameDisplay) userNameDisplay.textContent = name;
                    if (userAvatar) userAvatar.textContent = name.charAt(0).toUpperCase();

                    if (userQuotaDisplay && data.storage_metrics) {
                        const usedMb = data.storage_metrics.used_mb;
                        const maxMb = data.storage_metrics.max_mb;
                        const maxGb = Math.round((maxMb / 1024) * 10) / 10;
                        userQuotaDisplay.textContent = `${usedMb} MB / ${maxGb} GB`;
                    }
                }
            }
        } catch (e) {
            console.error("Failed to load stats:", e);
        }
    }


    async function loadVaultNotes() {
        try {
            notesList.innerHTML = `
                <div class="loading-spinner-wrap">
                    <div class="spinner"></div>
                    <span>Fetching vault notes...</span>
                </div>
            `;
            const res = await authFetch("/api/notes?limit=100");
            if (res.ok) {
                const data = await res.json();
                cachedNotes = data.notes || [];
                renderNotesList();
            } else {
                notesList.innerHTML = `<div class="loading-spinner-wrap"><span>Failed to load notes.</span></div>`;
            }
        } catch (e) {
            console.error("Failed to fetch notes:", e);
            notesList.innerHTML = `<div class="loading-spinner-wrap"><span>Error connecting to server.</span></div>`;
        }
    }

    function renderNotesList() {
        const query = vaultSearchInput.value.trim().toLowerCase();
        const filtered = cachedNotes.filter(note => {
            const matchesCat = !activeCategoryFilter || note.category === activeCategoryFilter;
            const matchesQuery = !query || 
                note.summary.toLowerCase().includes(query) || 
                note.tags.some(t => t.toLowerCase().includes(query));
            return matchesCat && matchesQuery;
        });

        if (filtered.length === 0) {
            notesList.innerHTML = `
                <div class="loading-spinner-wrap">
                    <span style="font-size: 1.5rem">📭</span>
                    <span>No notes found.</span>
                </div>
            `;
            return;
        }

        notesList.innerHTML = filtered.map(note => {
            const catLower = note.category.toLowerCase();
            return `
                <div class="note-item-card" onclick="openNoteModal('${note.category}', '${note.filename}')">
                    <div class="note-item-top">
                        <span class="badge badge-${catLower}">${note.category}</span>
                        <span class="note-item-meta">${note.mtime}</span>
                    </div>
                    <div class="note-item-title">${escapeHtml(note.summary)}</div>
                    <div class="note-item-meta">
                        ${note.has_media ? '📎 Has Attachment • ' : ''}
                        ${note.tags.length ? '#' + note.tags.slice(0, 2).join(' #') : ''}
                    </div>
                </div>
            `;
        }).join("");
    }

    function escapeHtml(str) {
        if (!str) return "";
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    // Global helper to set query example
    window.setQueryExample = function(text) {
        thoughtInput.value = text;
        autoResizeTextarea();
        thoughtInput.focus();
    };

    // Global helper for opening note modal
    window.openNoteModal = async function(category, filename) {
        try {
            const res = await authFetch(`/api/note/${category}/${filename}`);
            if (!res.ok) throw new Error("Could not load note");
            const data = await res.json();

            modalCategoryBadge.textContent = category;
            modalCategoryBadge.className = `badge badge-${category.toLowerCase()}`;
            modalTitle.textContent = filename.replace(/\.md$/, "");
            modalGdrivePath.textContent = data.gdrive_path;
            modalBody.innerHTML = renderMarkdown(data.content);
            modalDownloadLink.href = `/api/file/view?path=${category}/${filename}&download=true`;

            noteModal.classList.remove("hidden");
        } catch (e) {
            showToast("Failed to open note details: " + e.message, "error");
        }
    };

    window.closeNoteModal = function() {
        noteModal.classList.add("hidden");
    };

    if (btnCloseModal) {
        btnCloseModal.addEventListener("click", closeNoteModal);
    }

    noteModal.addEventListener("click", (e) => {
        if (e.target === noteModal) closeNoteModal();
    });

    // --- Mode Tabs Switching ---
    modeTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            modeTabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            currentMode = tab.dataset.mode;

            // Update placeholder
            switch (currentMode) {
                case "note":
                    thoughtInput.placeholder = "Capture a thought or note to save into PARA framework...";
                    break;
                case "ask":
                    thoughtInput.placeholder = "Ask a question about your Second Brain (RAG)...";
                    break;
                case "get":
                    thoughtInput.placeholder = "Enter document/file name or topic to retrieve and download...";
                    break;
                default:
                    thoughtInput.placeholder = "Capture a thought, note, paste screenshot (Ctrl+V), or ask anything...";
                    break;
            }
            thoughtInput.focus();
        });
    });

    // --- Auto-resize Textarea ---
    function autoResizeTextarea() {
        thoughtInput.style.height = "auto";
        const newHeight = Math.min(thoughtInput.scrollHeight, 160);
        thoughtInput.style.height = `${newHeight}px`;
    }

    thoughtInput.addEventListener("input", autoResizeTextarea);

    thoughtInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submitCapture();
        }
    });

    // --- File Attachment Handling ---
    function setAttachedFile(file) {
        if (!file) return;
        activeAttachedFile = file;

        previewFilename.textContent = file.name;
        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        const typeDesc = file.type || "File";
        previewMeta.textContent = `${sizeMb} MB • ${typeDesc}`;

        previewMediaContainer.innerHTML = "";
        if (file.type.startsWith("image/")) {
            const img = document.createElement("img");
            img.className = "preview-thumb";
            const reader = new FileReader();
            reader.onload = (e) => { img.src = e.target.result; };
            reader.readAsDataURL(file);
            previewMediaContainer.appendChild(img);
        } else if (file.type.startsWith("audio/")) {
            previewMediaContainer.innerHTML = `<span style="font-size:1.2rem">🎙️</span>`;
        } else if (file.type.includes("pdf")) {
            previewMediaContainer.innerHTML = `<span style="font-size:1.2rem">📄</span>`;
        } else {
            previewMediaContainer.innerHTML = `<span style="font-size:1.2rem">📎</span>`;
        }

        attachmentStrip.classList.remove("hidden");
    }

    function clearAttachedFile() {
        activeAttachedFile = null;
        fileInput.value = "";
        attachmentStrip.classList.add("hidden");
    }

    btnRemoveAttachment.addEventListener("click", clearAttachedFile);

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
            setAttachedFile(e.target.files[0]);
        }
    });

    // --- Drag and Drop File Support ---
    let dragCounter = 0;
    window.addEventListener("dragenter", (e) => {
        e.preventDefault();
        dragCounter++;
        dropOverlay.classList.remove("hidden");
    });

    window.addEventListener("dragleave", (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            dropOverlay.classList.add("hidden");
        }
    });

    window.addEventListener("dragover", (e) => {
        e.preventDefault();
    });

    window.addEventListener("drop", (e) => {
        e.preventDefault();
        dragCounter = 0;
        dropOverlay.classList.add("hidden");

        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            setAttachedFile(e.dataTransfer.files[0]);
            showToast(`Attached: ${e.dataTransfer.files[0].name}`, "info");
        }
    });

    // --- Clipboard Paste (Ctrl+V) Image Support ---
    window.addEventListener("paste", (e) => {
        if (e.clipboardData && e.clipboardData.items) {
            for (let i = 0; i < e.clipboardData.items.length; i++) {
                const item = e.clipboardData.items[i];
                if (item.type.indexOf("image") !== -1) {
                    const blob = item.getAsFile();
                    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
                    const pastedFile = new File([blob], `pasted_screenshot_${timestamp}.png`, { type: blob.type });
                    setAttachedFile(pastedFile);
                    showToast("Pasted screenshot attached from clipboard! 🖼️", "success");
                    break;
                }
            }
        }
    });

    // --- Voice Memo Live Audio Recording ---
    async function startVoiceRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showToast("Microphone access is not supported by your browser.", "error");
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks = [];
            
            // Choose supported mimeType
            let mimeType = "audio/webm";
            if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
                mimeType = "audio/webm;codecs=opus";
            } else if (MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")) {
                mimeType = "audio/ogg;codecs=opus";
            }

            mediaRecorder = new MediaRecorder(stream, { mimeType });
            
            mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) {
                    audioChunks.push(e.data);
                }
            };

            mediaRecorder.start(200);
            recordingSeconds = 0;
            recordingTimer.textContent = "00:00";
            voiceRecorderBar.classList.remove("hidden");
            btnMicRecord.style.color = "var(--danger)";

            recordingInterval = setInterval(() => {
                recordingSeconds++;
                const mins = String(Math.floor(recordingSeconds / 60)).padStart(2, "0");
                const secs = String(recordingSeconds % 60).padStart(2, "0");
                recordingTimer.textContent = `${mins}:${secs}`;
            }, 1000);

        } catch (err) {
            console.error("Microphone permission denied:", err);
            showToast("Microphone access denied or unavailable: " + err.message, "error");
        }
    }

    function stopVoiceRecording(save = true) {
        if (!mediaRecorder) return;
        clearInterval(recordingInterval);

        mediaRecorder.onstop = () => {
            if (save && audioChunks.length > 0) {
                const ext = mediaRecorder.mimeType.includes("ogg") ? "ogg" : "webm";
                const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
                const now = new Date().toISOString().replace(/[:.]/g, "-");
                const recordedFile = new File([audioBlob], `voice_memo_${now}.${ext}`, { type: audioBlob.type });
                setAttachedFile(recordedFile);
                showToast("Voice memo recorded! Ready to submit.", "success");
            }
            // Stop all audio tracks to release the microphone
            if (mediaRecorder.stream) {
                mediaRecorder.stream.getTracks().forEach(track => track.stop());
            }
            mediaRecorder = null;
            audioChunks = [];
        };

        mediaRecorder.stop();
        voiceRecorderBar.classList.add("hidden");
        btnMicRecord.style.color = "";
    }

    btnMicRecord.addEventListener("click", () => {
        if (!mediaRecorder) {
            startVoiceRecording();
        } else {
            stopVoiceRecording(true);
        }
    });

    btnCancelRecording.addEventListener("click", () => {
        stopVoiceRecording(false);
        showToast("Voice recording cancelled.", "info");
    });

    btnStopAndSendRecording.addEventListener("click", () => {
        stopVoiceRecording(true);
    });

    // --- Vault Explorer Drawer Toggle ---
    toggleExplorerBtn.addEventListener("click", () => {
        vaultDrawer.classList.toggle("open");
        if (vaultDrawer.classList.contains("open")) {
            loadVaultNotes();
            vaultSearchInput.focus();
        }
    });

    btnCloseDrawer.addEventListener("click", () => {
        vaultDrawer.classList.remove("open");
    });

    vaultSearchInput.addEventListener("input", renderNotesList);

    catPills.forEach(pill => {
        pill.addEventListener("click", () => {
            catPills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            activeCategoryFilter = pill.dataset.cat || "";
            renderNotesList();
        });
    });

    // --- Submit Capture ---
    async function submitCapture() {
        const text = thoughtInput.value.trim();
        const file = activeAttachedFile;

        if (!text && !file) {
            showToast("Please enter a note/question or attach media/audio.", "info");
            thoughtInput.focus();
            return;
        }

        // If recording is active, stop and save it first
        if (mediaRecorder) {
            stopVoiceRecording(true);
        }

        // Clear input deck right away
        thoughtInput.value = "";
        autoResizeTextarea();
        clearAttachedFile();

        // 1. Render User Message in Feed
        const userMessageId = "msg-" + Date.now();
        renderUserMessage(userMessageId, text, file);

        // 2. Render Thinking Indicator
        const thinkingId = "thinking-" + Date.now();
        renderThinkingCard(thinkingId);

        // Prepare FormData
        const formData = new FormData();
        if (text) formData.append("text", text);
        if (file) formData.append("file", file);
        formData.append("mode", currentMode);

        try {
            btnSubmit.disabled = true;
            const res = await authFetch("/api/capture", {
                method: "POST",
                body: formData
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Server error processing request");
            }

            const data = await res.json();
            removeElement(thinkingId);

            // Handle Response Type
            if (data.type === "saved") {
                renderSavedCard(data);
                showToast(`Saved to PARA: ${data.category}`, "success");
            } else if (data.type === "query") {
                renderRagQueryCard(data);
            } else if (data.type === "retrieval") {
                renderRetrievalCard(data);
            }

            // Refresh system stats and notes list
            loadStats();

        } catch (err) {
            console.error("Submission failed:", err);
            removeElement(thinkingId);
            renderErrorCard(err.message);
            showToast(err.message, "error");
        } finally {
            btnSubmit.disabled = false;
            thoughtInput.focus();
        }
    }

    btnSubmit.addEventListener("click", submitCapture);

    function removeElement(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function renderUserMessage(id, text, file) {
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const card = document.createElement("div");
        card.id = id;
        card.className = "feed-item user-message";

        let fileBadge = "";
        if (file) {
            let icon = "📎";
            if (file.type.startsWith("image/")) icon = "🖼️";
            else if (file.type.startsWith("audio/")) icon = "🎙️";
            else if (file.type.includes("pdf")) icon = "📄";
            fileBadge = `<div class="user-attached-preview">${icon} <span>${escapeHtml(file.name)}</span></div>`;
        }

        card.innerHTML = `
            <div class="feed-item-header">
                <span class="badge" style="background: rgba(255,255,255,0.06); color: #cbd5e1;">You</span>
                <span class="feed-timestamp">${timeStr}</span>
            </div>
            ${text ? `<div class="user-message-text">${escapeHtml(text)}</div>` : ''}
            ${fileBadge}
        `;

        interactionFeed.appendChild(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function renderThinkingCard(id) {
        const card = document.createElement("div");
        card.id = id;
        card.className = "feed-item";
        card.innerHTML = `
            <div class="feed-item-header">
                <span class="badge badge-purple">AI Core</span>
                <span class="feed-timestamp">Thinking...</span>
            </div>
            <div class="loading-spinner-wrap" style="padding: 16px;">
                <div class="spinner"></div>
                <span style="color: var(--text-secondary); font-size: 0.9rem;">Processing multimodal thought with Gemini 1.5 Flash...</span>
            </div>
        `;
        interactionFeed.appendChild(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function renderSavedCard(data) {
        const card = document.createElement("div");
        card.className = "feed-item";
        const catLower = (data.category || "resources").toLowerCase();
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        let mediaBlock = "";
        if (data.media_url) {
            if (data.media_type === "Images") {
                mediaBlock = `
                    <div class="media-display-box">
                        <img src="${data.media_url}" class="media-image-preview" alt="Attached Image" loading="lazy">
                    </div>
                `;
            } else if (data.media_type === "Audio") {
                mediaBlock = `
                    <div class="media-display-box">
                        <audio controls class="media-audio-player" src="${data.media_url}"></audio>
                    </div>
                `;
            } else {
                mediaBlock = `
                    <div class="media-display-box">
                        <div class="media-doc-card">
                            <span>📄 Attached Document</span>
                            <a href="${data.media_download}" class="btn btn-secondary btn-sm" download>Download File</a>
                        </div>
                    </div>
                `;
            }
        }

        const tagsHtml = (data.tags || []).map(t => `<span class="tag-pill">#${escapeHtml(t)}</span>`).join("");

        card.innerHTML = `
            <div class="feed-item-header">
                <span class="badge badge-${catLower}">${escapeHtml(data.category)}</span>
                <span class="feed-timestamp">${timeStr}</span>
            </div>
            <div class="saved-note-title">📝 ${escapeHtml(data.summary)}</div>
            ${tagsHtml ? `<div class="saved-note-tags">${tagsHtml}</div>` : ''}
            ${mediaBlock}
            <div class="saved-note-content">${escapeHtml(data.content)}</div>
            <div class="saved-note-paths">
                <div class="path-row">
                    <span>📄 Note:</span>
                    <span class="path-code">${escapeHtml(data.note_gdrive)}</span>
                </div>
                ${data.media_gdrive ? `
                <div class="path-row">
                    <span>📎 Media:</span>
                    <span class="path-code">${escapeHtml(data.media_gdrive)}</span>
                </div>` : ''}
            </div>
            <div class="saved-note-actions">
                <a href="${data.note_download}" class="btn btn-secondary btn-sm" download>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                    Download Markdown
                </a>
                ${data.media_download ? `
                <a href="${data.media_download}" class="btn btn-secondary btn-sm" download>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                    Download Attachment
                </a>` : ''}
            </div>
        `;

        interactionFeed.appendChild(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function renderRagQueryCard(data) {
        const card = document.createElement("div");
        card.className = "feed-item";
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        let sourcesHtml = "";
        if (data.sources && data.sources.length > 0) {
            const sourceItems = data.sources.map(s => {
                const catLower = (s.category || "resources").toLowerCase();
                return `
                    <div class="source-item">
                        <div class="source-title-row">
                            <span class="source-title">${escapeHtml(s.summary)}</span>
                            <span class="badge badge-${catLower}">${escapeHtml(s.category)}</span>
                        </div>
                        <div class="source-snippet">${escapeHtml(s.snippet)}</div>
                        <div class="source-links">
                            <span>📁 <code>${escapeHtml(s.gdrive_path)}</code></span>
                            ${s.file_url ? `<a href="${s.file_url}&download=true" class="chip" download>Download</a>` : ''}
                            ${s.media_url ? `<a href="${s.media_url}&download=true" class="chip" download>Attached File</a>` : ''}
                        </div>
                    </div>
                `;
            }).join("");

            sourcesHtml = `
                <div class="sources-accordion">
                    <div class="sources-header">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                            <polyline points="14 2 14 8 20 8"></polyline>
                        </svg>
                        <span>Retrieved Context Notes (${data.sources.length})</span>
                    </div>
                    ${sourceItems}
                </div>
            `;
        }

        let matchedFileBlock = "";
        if (data.matched_file) {
            matchedFileBlock = `
                <div class="retrieval-card">
                    <div>
                        <strong>📦 Attached Document:</strong> ${escapeHtml(data.matched_file.name)}
                        <div style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono); margin-top:2px;">
                            ${escapeHtml(data.matched_file.gdrive_path)}
                        </div>
                    </div>
                    <a href="${data.matched_file.url}" class="btn btn-primary btn-sm" download>Download File</a>
                </div>
            `;
        }

        card.innerHTML = `
            <div class="feed-item-header">
                <span class="badge badge-purple">RAG Answer</span>
                <span class="feed-timestamp">${timeStr}</span>
            </div>
            <div class="rag-temporal-badge">
                <span>🗓️</span>
                <span>Context calculated with today's temporal awareness</span>
            </div>
            <div class="rag-answer-body">${renderMarkdown(data.answer)}</div>
            ${matchedFileBlock}
            ${sourcesHtml}
        `;

        interactionFeed.appendChild(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function renderRetrievalCard(data) {
        const card = document.createElement("div");
        card.className = "feed-item";
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        if (!data.found) {
            card.innerHTML = `
                <div class="feed-item-header">
                    <span class="badge" style="background: rgba(239,68,68,0.15); color: #f87171;">Not Found</span>
                    <span class="feed-timestamp">${timeStr}</span>
                </div>
                <p style="color: var(--text-secondary);">${escapeHtml(data.message)}</p>
            `;
        } else {
            const catLower = (data.category || "resources").toLowerCase();
            card.innerHTML = `
                <div class="feed-item-header">
                    <span class="badge badge-${catLower}">${escapeHtml(data.category)}</span>
                    <span class="feed-timestamp">${timeStr}</span>
                </div>
                <div class="saved-note-title">🎯 ${escapeHtml(data.summary)}</div>
                <div class="saved-note-paths" style="margin-bottom: 12px;">
                    <div class="path-row">
                        <span>📄 GDrive Note:</span>
                        <span class="path-code">${escapeHtml(data.note_gdrive)}</span>
                    </div>
                    ${data.media_gdrive ? `
                    <div class="path-row">
                        <span>📦 GDrive File:</span>
                        <span class="path-code">${escapeHtml(data.media_gdrive)}</span>
                    </div>` : ''}
                </div>
                <div class="retrieval-card">
                    <div>
                        <strong>${escapeHtml(data.media_name || data.summary)}</strong>
                        <p style="font-size:0.78rem; color:var(--text-muted); margin:0;">Direct download link from Second Brain vault</p>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        ${data.media_url ? `<a href="${data.media_url}" class="btn btn-primary btn-sm" download>Download File</a>` : ''}
                        ${data.note_url ? `<a href="${data.note_url}" class="btn btn-secondary btn-sm" download>Download Note</a>` : ''}
                    </div>
                </div>
            `;
        }

        interactionFeed.appendChild(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function renderErrorCard(message) {
        const card = document.createElement("div");
        card.className = "feed-item";
        card.style.borderLeft = "3px solid var(--danger)";
        card.innerHTML = `
            <div class="feed-item-header">
                <span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171;">Error</span>
                <span class="feed-timestamp">Just now</span>
            </div>
            <p style="color: #fca5a5; font-size: 0.9rem;">${escapeHtml(message)}</p>
        `;
        interactionFeed.appendChild(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // --- Auth Form & Lock Event Listeners ---
    if (authForm) {
        authForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const token = (authPassphrase.value || "").trim();
            if (!token) return;

            hideAuthError();
            const btn = document.getElementById("btnUnlockVault");
            if (btn) btn.disabled = true;

            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ token: token })
                });

                if (res.ok) {
                    const data = await res.json();
                    setAuthToken(data.token, rememberMe ? rememberMe.checked : true);
                    showAuthGate(false);
                    showToast("Vault Unlocked Successfully", "success");
                    loadStats();
                    loadVaultNotes();
                } else {
                    const err = await res.json().catch(() => ({}));
                    showAuthError(err.detail || "Invalid access key or passphrase.");
                }
            } catch (err) {
                showAuthError("Connection error. Is the server running?");
            } finally {
                if (btn) btn.disabled = false;
            }
        });
    }

    if (btnToggleAuthVisibility && authPassphrase) {
        btnToggleAuthVisibility.addEventListener("click", () => {
            const isPassword = authPassphrase.type === "password";
            authPassphrase.type = isPassword ? "text" : "password";
        });
    }

    if (btnLockVault) {
        btnLockVault.addEventListener("click", async () => {
            try {
                await fetch("/api/auth/logout", { method: "POST" });
            } catch (e) {}
            clearAuthToken();
            if (authPassphrase) authPassphrase.value = "";
            showAuthGate(true);
            showToast("Vault Locked", "info");
        });
    }

    // Register Service Worker for PWA
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js").then(
                (reg) => console.log("Service Worker registered successfully:", reg.scope),
                (err) => console.warn("Service Worker registration failed:", err)
            );
        });
    }

    // Initial Auth Verification & Data Load
    async function initAuth() {
        try {
            const res = await authFetch("/api/auth/verify");
            if (res.ok) {
                const data = await res.json();
                if (data.authenticated) {
                    showAuthGate(false);
                    loadStats();
                    return;
                }
            }
        } catch (e) {
            console.warn("Auth check error:", e);
        }
        showAuthGate(true);
    }

    initAuth();
});
