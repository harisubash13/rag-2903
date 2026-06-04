document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const apiKeyInput = document.getElementById("api-key-input");
    const saveKeyBtn = document.getElementById("save-key-btn");
    const apiStatusBadge = document.getElementById("api-status-badge");
    const toggleConfig = document.getElementById("toggle-config");
    const configCard = document.querySelector(".config-card");
    
    // User Profile Switcher Elements
    const profileNameInput = document.getElementById("profile-name-input");
    const switchProfileBtn = document.getElementById("switch-profile-btn");
    const activeProfileName = document.getElementById("active-profile-name");
    
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const browseBtn = document.getElementById("browse-btn");
    const uploadProgressContainer = document.getElementById("upload-progress-container");
    const uploadFilename = document.getElementById("upload-filename");
    const uploadPercent = document.getElementById("upload-percent");
    const uploadProgressBar = document.getElementById("upload-progress-bar");
    
    const filesList = document.getElementById("files-list");
    const filesCount = document.getElementById("files-count");
    const clearDbBtn = document.getElementById("clear-db-btn");
    
    const statFiles = document.getElementById("stat-files");
    const statChunks = document.getElementById("stat-chunks");
    
    const chatMessages = document.getElementById("chat-messages");
    const welcomeScreen = document.getElementById("welcome-screen");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const sendBtn = document.getElementById("send-btn");
    const suggestionChips = document.querySelectorAll(".suggestion-chip");

    // Global State
    let apiKey = localStorage.getItem("gemini_api_key") || "";
    let activeProfile = localStorage.getItem("active_profile") || "default";
    let isGenerating = false;

    // Initialize UI
    if (apiKey) {
        apiKeyInput.value = apiKey;
    }
    activeProfileName.textContent = activeProfile;
    
    // Configure Lucide Icons
    lucide.createIcons();

    // Check backend status and load initial files
    checkSystemStatus();
    loadFilesList();

    // 1. API Configuration Logic
    toggleConfig.addEventListener("click", () => {
        configCard.classList.toggle("collapsed");
    });

    // Profile Switcher Logic
    switchProfileBtn.addEventListener("click", () => {
        const profileVal = profileNameInput.value.trim().toLowerCase();
        if (!profileVal) {
            showToast("Please enter a valid profile name", "error");
            return;
        }
        
        // Sanitize name: alphanumeric and underscores only
        const sanitized = profileVal.replace(/[^a-zA-Z0-9_]/g, "");
        if (!sanitized) {
            showToast("Profile name must contain alphanumeric characters or underscores only", "error");
            return;
        }
        
        activeProfile = sanitized;
        localStorage.setItem("active_profile", activeProfile);
        activeProfileName.textContent = activeProfile;
        profileNameInput.value = "";
        
        showToast(`Switched to profile: ${activeProfile}`, "success");
        
        // Clear chat and return to welcome screen
        const messageBubbles = chatMessages.querySelectorAll(".message");
        messageBubbles.forEach(msg => msg.remove());
        welcomeScreen.style.display = "flex";
        
        // Refresh state for new profile
        checkSystemStatus();
        loadFilesList();
    });

    saveKeyBtn.addEventListener("click", () => {
        const key = apiKeyInput.value.trim();
        apiKey = key;
        localStorage.setItem("gemini_api_key", key);
        
        // Show saved feedback briefly
        const icon = saveKeyBtn.querySelector("i");
        saveKeyBtn.innerHTML = '<i data-lucide="check" style="color: var(--accent-green)"></i>';
        lucide.createIcons();
        
        setTimeout(() => {
            saveKeyBtn.innerHTML = '<i data-lucide="save"></i>';
            lucide.createIcons();
        }, 1500);

        checkSystemStatus();
    });

    async function checkSystemStatus() {
        try {
            const headers = {
                "X-User-Profile": activeProfile
            };
            if (apiKey) {
                headers["X-Gemini-API-Key"] = apiKey;
            }
            const res = await fetch("/api/status", { headers });
            if (res.ok) {
                const data = await res.json();
                updateSystemStatusUI(data);
            }
        } catch (err) {
            console.error("Failed to connect to backend:", err);
            apiStatusBadge.textContent = "Offline";
            apiStatusBadge.className = "badge badge-error";
            sendBtn.disabled = true;
        }
    }

    function updateSystemStatusUI(data) {
        if (data.api_key_configured) {
            apiStatusBadge.textContent = "Connected";
            apiStatusBadge.className = "badge badge-success";
            sendBtn.disabled = isGenerating;
            
            // Auto collapse config if configured
            if (apiKey && !configCard.classList.contains("collapsed")) {
                configCard.classList.add("collapsed");
            }
        } else {
            apiStatusBadge.textContent = "Key Missing";
            apiStatusBadge.className = "badge badge-error";
            // Expand configuration card to prompt user
            configCard.classList.remove("collapsed");
            sendBtn.disabled = true;
        }

        // Update stats
        statFiles.textContent = `${data.files_count} file${data.files_count !== 1 ? 's' : ''}`;
        statChunks.textContent = `${data.chunks_count} chunk${data.chunks_count !== 1 ? 's' : ''}`;
        filesCount.textContent = data.files_count;
        
        // Enable/disable reset database button
        clearDbBtn.disabled = data.files_count === 0;
    }

    // 2. Drag & Drop File Upload Logic
    browseBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => handleSelectedFiles(e.target.files));

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    ["dragleave", "drop"].forEach(event => {
        dropZone.addEventListener(event, () => {
            dropZone.classList.remove("dragover");
        });
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        if (e.dataTransfer.files.length > 0) {
            handleSelectedFiles(e.dataTransfer.files);
        }
    });

    async function handleSelectedFiles(files) {
        if (files.length === 0) return;
        
        // Upload files sequentially to manage progress bar accurately
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const name = file.name;
            const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
            
            if (!['.pdf', '.xlsx', '.txt'].includes(ext)) {
                showToast(`Unsupported file type: ${name}. Only PDF, XLSX, and TXT are allowed.`, "error");
                continue;
            }
            
            await uploadFile(file);
        }
        
        // Refresh statuses
        await checkSystemStatus();
        await loadFilesList();
    }

    function uploadFile(file) {
        return new Promise((resolve) => {
            const xhr = new XMLHttpRequest();
            const formData = new FormData();
            formData.append("file", file);

            // Setup UI for upload start
            uploadProgressContainer.style.display = "block";
            uploadFilename.textContent = file.name;
            uploadPercent.textContent = "0%";
            uploadProgressBar.style.width = "0%";

            xhr.upload.addEventListener("progress", (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    uploadPercent.textContent = `${percent}%`;
                    uploadProgressBar.style.width = `${percent}%`;
                }
            });

            xhr.addEventListener("load", () => {
                uploadProgressContainer.style.display = "none";
                if (xhr.status >= 200 && xhr.status < 300) {
                    const response = JSON.parse(xhr.responseText);
                    showToast(response.message, "success");
                } else {
                    let errMsg = "Upload failed";
                    try {
                        const errData = JSON.parse(xhr.responseText);
                        errMsg = errData.detail || errMsg;
                    } catch(e) {}
                    showToast(`${file.name}: ${errMsg}`, "error");
                }
                resolve();
            });

            xhr.addEventListener("error", () => {
                uploadProgressContainer.style.display = "none";
                showToast(`Network error uploading: ${file.name}`, "error");
                resolve();
            });

            xhr.open("POST", "/api/upload");
            xhr.setRequestHeader("X-User-Profile", activeProfile);
            if (apiKey) {
                xhr.setRequestHeader("X-Gemini-API-Key", apiKey);
            }
            xhr.send(formData);
        });
    }

    // 3. Files Management (List & Clear)
    async function loadFilesList() {
        try {
            const res = await fetch("/api/files", {
                headers: { "X-User-Profile": activeProfile }
            });
            if (res.ok) {
                const files = await res.json();
                renderFilesList(files);
            }
        } catch (err) {
            console.error("Failed to load files list:", err);
        }
    }

    function renderFilesList(files) {
        filesList.innerHTML = "";
        
        if (files.length === 0) {
            filesList.innerHTML = `
                <div class="empty-files-message">
                    <i data-lucide="files" class="watermark-icon"></i>
                    <p>No documents ingested yet</p>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        files.forEach(file => {
            const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase().replace('.', '');
            const item = document.createElement("div");
            item.className = "file-item animate-fade-in";
            
            // Choose icon based on file type
            let iconName = "file-text";
            if (ext === "pdf") iconName = "file-text";
            else if (ext === "xlsx") iconName = "table";
            
            item.innerHTML = `
                <div class="file-item-left">
                    <i data-lucide="${iconName}" class="file-type-icon ${ext}"></i>
                    <div class="file-details">
                        <span class="file-name" title="${file.name}">${file.name}</span>
                        <span class="file-meta">${file.chunks} chunks</span>
                    </div>
                </div>
            `;
            filesList.appendChild(item);
        });
        
        lucide.createIcons();
    }

    clearDbBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to reset the vector database for this profile? All ingested files and indexed chunks will be deleted permanently.")) {
            return;
        }
        
        try {
            const res = await fetch("/api/clear", { 
                method: "POST",
                headers: { "X-User-Profile": activeProfile }
            });
            if (res.ok) {
                showToast("Database successfully cleared.", "success");
                
                // Clear chat messages and show welcome
                const messageBubbles = chatMessages.querySelectorAll(".message");
                messageBubbles.forEach(msg => msg.remove());
                welcomeScreen.style.display = "flex";
                
                await checkSystemStatus();
                await loadFilesList();
            } else {
                showToast("Failed to clear database.", "error");
            }
        } catch (err) {
            console.error("Error clearing DB:", err);
            showToast("Failed to clear database due to network error.", "error");
        }
    });

    // 4. Conversational Chat Console Logic
    
    // Auto-grow textarea
    chatInput.addEventListener("input", function() {
        this.style.height = "auto";
        this.style.height = (this.scrollHeight) + "px";
    });

    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event("submit"));
        }
    });

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const queryText = chatInput.value.trim();
        if (!queryText || isGenerating) return;

        // Reset input height
        chatInput.value = "";
        chatInput.style.height = "auto";

        // Hide welcome screen
        welcomeScreen.style.display = "none";

        // 1. Add User Message
        appendMessage(queryText, "user");
        
        // 2. Add Loading Indicator
        const loadingId = appendLoadingIndicator();
        
        // 3. Set Generating status
        setGeneratingState(true);
        
        try {
            const headers = { 
                "Content-Type": "application/json",
                "X-User-Profile": activeProfile
            };
            if (apiKey) {
                headers["X-Gemini-API-Key"] = apiKey;
            }
            
            const res = await fetch("/api/query", {
                method: "POST",
                headers: headers,
                body: JSON.stringify({ query: queryText })
            });

            removeLoadingIndicator(loadingId);

            if (res.ok) {
                const data = await res.json();
                appendMessage(data.answer, "bot", data.sources);
            } else {
                let errorMsg = "Something went wrong.";
                try {
                    const errData = await res.json();
                    errorMsg = errData.detail || errorMsg;
                } catch(e) {}
                appendMessage(`**Error:** ${errorMsg}`, "bot-error");
            }
        } catch (err) {
            console.error("Query failed:", err);
            removeLoadingIndicator(loadingId);
            appendMessage("**Network Error:** Failed to connect to server. Please check your backend connection.", "bot-error");
        } finally {
            setGeneratingState(false);
        }
    });

    // Handle suggestion chips
    suggestionChips.forEach(chip => {
        chip.addEventListener("click", () => {
            const prompt = chip.getAttribute("data-prompt");
            if (prompt) {
                chatInput.value = prompt;
                chatInput.style.height = "auto";
                chatInput.style.height = (chatInput.scrollHeight) + "px";
                chatInput.focus();
                
                // If API is configured, auto-submit
                if (apiStatusBadge.textContent === "Connected") {
                    chatForm.dispatchEvent(new Event("submit"));
                }
            }
        });
    });

    function setGeneratingState(generating) {
        isGenerating = generating;
        chatInput.disabled = generating;
        sendBtn.disabled = generating || apiStatusBadge.textContent !== "Connected";
        
        if (generating) {
            chatInput.placeholder = "OmniReader is thinking...";
        } else {
            chatInput.placeholder = "Ask a question about your ingested documents...";
            chatInput.focus();
        }
    }

    function appendMessage(text, sender, sources = []) {
        const messageContainer = document.createElement("div");
        messageContainer.className = `message message-${sender}`;
        
        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        
        // Render content
        if (sender === "user") {
            bubble.textContent = text;
        } else {
            // Render markdown for bot answers
            bubble.innerHTML = marked.parse(text);
            // Highlight code blocks
            bubble.querySelectorAll("pre code").forEach(block => {
                hljs.highlightBlock(block);
            });
        }
        
        messageContainer.appendChild(bubble);

        // Append Sources if present
        if (sources && sources.length > 0) {
            const sourcesDiv = document.createElement("div");
            sourcesDiv.className = "message-sources";
            
            const toggleId = `toggle-${Math.random().toString(36).substr(2, 9)}`;
            const listId = `list-${Math.random().toString(36).substr(2, 9)}`;
            
            const sourcesToggle = document.createElement("div");
            sourcesToggle.className = "sources-toggle";
            sourcesToggle.id = toggleId;
            sourcesToggle.innerHTML = `
                <i data-lucide="chevron-down"></i>
                <span>View Sources (${sources.length})</span>
            `;
            
            const sourcesList = document.createElement("div");
            sourcesList.className = "sources-list";
            sourcesList.id = listId;
            sourcesList.style.display = "none";
            
            sources.forEach((src, idx) => {
                const sourceCard = document.createElement("div");
                sourceCard.className = "source-card";
                
                const meta = src.metadata;
                let refLabel = `Chunk #${idx+1} | Source: ${meta.source}`;
                if (meta.page) refLabel += ` (Page ${meta.page})`;
                else if (meta.sheet) refLabel += ` (Sheet '${meta.sheet}', Rows ${meta.rows})`;
                
                sourceCard.innerHTML = `
                    <div class="source-card-header">
                        <span>${refLabel}</span>
                        <span class="source-badge">Similarity: ${Math.round(src.similarity * 100)}%</span>
                    </div>
                    <div class="source-content">${escapeHTML(src.text)}</div>
                `;
                sourcesList.appendChild(sourceCard);
            });
            
            sourcesToggle.addEventListener("click", () => {
                const isActive = sourcesToggle.classList.toggle("active");
                sourcesList.style.display = isActive ? "flex" : "none";
                
                // Toggle icon
                const icon = sourcesToggle.querySelector("i");
                if (isActive) {
                    icon.setAttribute("data-lucide", "chevron-up");
                } else {
                    icon.setAttribute("data-lucide", "chevron-down");
                }
                lucide.createIcons();
                
                // Scroll main chat container down to show sources
                setTimeout(() => {
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }, 50);
            });
            
            sourcesDiv.appendChild(sourcesToggle);
            sourcesDiv.appendChild(sourcesList);
            messageContainer.appendChild(sourcesDiv);
        }
        
        chatMessages.appendChild(messageContainer);
        lucide.createIcons();
        
        // Auto scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendLoadingIndicator() {
        const id = `loading-${Math.random().toString(36).substr(2, 9)}`;
        const messageContainer = document.createElement("div");
        messageContainer.className = `message message-bot`;
        messageContainer.id = id;
        
        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        
        const typingIndicator = document.createElement("div");
        typingIndicator.className = "typing-indicator";
        typingIndicator.innerHTML = `
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        `;
        
        bubble.appendChild(typingIndicator);
        messageContainer.appendChild(bubble);
        chatMessages.appendChild(messageContainer);
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return id;
    }

    function removeLoadingIndicator(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    // 5. Utility Functions
    function escapeHTML(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function showToast(message, type = "success") {
        // Create simple floating toast element
        const toast = document.createElement("div");
        toast.className = `toast toast-${type} animate-fade-in`;
        
        // Toast style definitions in CSS style but applied inline or created dynamically
        toast.style.position = "fixed";
        toast.style.bottom = "24px";
        toast.style.right = "24px";
        toast.style.zIndex = "1000";
        toast.style.padding = "12px 20px";
        toast.style.borderRadius = "8px";
        toast.style.fontSize = "0.85rem";
        toast.style.fontWeight = "500";
        toast.style.color = "var(--text-primary)";
        toast.style.display = "flex";
        toast.style.alignItems = "center";
        toast.style.gap = "8px";
        toast.style.boxShadow = "var(--shadow-soft)";
        
        let iconName = "check-circle";
        if (type === "success") {
            toast.style.background = "rgba(16, 185, 129, 0.95)";
            toast.style.border = "1px solid rgba(16, 185, 129, 0.2)";
            iconName = "check-circle";
        } else {
            toast.style.background = "rgba(239, 68, 68, 0.95)";
            toast.style.border = "1px solid rgba(239, 68, 68, 0.2)";
            iconName = "alert-circle";
        }
        
        toast.innerHTML = `<i data-lucide="${iconName}" style="width: 16px; height: 16px;"></i><span>${message}</span>`;
        document.body.appendChild(toast);
        lucide.createIcons();
        
        // Fade out and remove
        setTimeout(() => {
            toast.style.transition = "opacity 0.5s ease-out, transform 0.5s ease-out";
            toast.style.opacity = "0";
            toast.style.transform = "translateY(10px)";
            setTimeout(() => toast.remove(), 500);
        }, 3000);
    }
});
