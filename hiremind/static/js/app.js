const themeToggleButtons = Array.from(document.querySelectorAll("[data-theme-toggle]"));
const themeIcons = Array.from(document.querySelectorAll("[data-theme-icon]"));
const globalSearchInput = document.getElementById("candidateGlobalSearch");

function applyTheme(theme) {
    const isDark = theme === "dark";
    document.body.classList.toggle("dark", isDark);
    document.body.classList.toggle("dark-mode", isDark);
    themeIcons.forEach((icon) => {
        icon.textContent = isDark ? "☀" : "🌙";
    });
}

function initializeThemeToggle() {
    const savedTheme = localStorage.getItem("theme");
    const initialTheme = savedTheme === "dark" ? "dark" : "light";
    applyTheme(initialTheme);

    if (!themeToggleButtons.length) {
        return;
    }

    themeToggleButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const nextTheme = document.body.classList.contains("dark") || document.body.classList.contains("dark-mode") ? "light" : "dark";
            localStorage.setItem("theme", nextTheme);
            applyTheme(nextTheme);
        });
    });
}

function focusGlobalSearch() {
    if (!globalSearchInput) {
        return;
    }

    globalSearchInput.focus();
    globalSearchInput.select();
}

function initializeSearchShortcut() {
    if (!globalSearchInput) {
        return;
    }

    document.addEventListener("keydown", (event) => {
        const activeTag = document.activeElement?.tagName;
        const isTypingField = activeTag === "INPUT" || activeTag === "TEXTAREA" || document.activeElement?.isContentEditable;

        if (event.key.toLowerCase() === "k" && !event.ctrlKey && !event.metaKey && !event.altKey && !isTypingField) {
            event.preventDefault();
            focusGlobalSearch();
        }

        if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !isTypingField) {
            event.preventDefault();
            focusGlobalSearch();
        }
    });
}

function initializeSettingsSaveBar() {
    const form = document.querySelector("[data-settings-form]");
    const saveBar = document.querySelector("[data-settings-savebar]");

    if (!form || !saveBar) {
        return;
    }

    const trackedFields = Array.from(form.elements).filter((field) => {
        if (!field.name || field.disabled) {
            return false;
        }

        const type = (field.type || "").toLowerCase();
        return type !== "hidden" && type !== "submit" && type !== "button";
    });

    const snapshotField = (field) => {
        const type = (field.type || "").toLowerCase();

        if (type === "checkbox" || type === "radio") {
            return field.checked;
        }

        if (type === "file") {
            return field.files?.length ? Array.from(field.files).map((file) => `${file.name}:${file.size}`).join("|") : "";
        }

        return field.value;
    };

    const initialState = new Map(trackedFields.map((field) => [field.name, snapshotField(field)]));

    const updateSaveBar = () => {
        const isDirty = trackedFields.some((field) => snapshotField(field) !== initialState.get(field.name));
        saveBar.classList.toggle("is-visible", isDirty);
    };

    trackedFields.forEach((field) => {
        field.addEventListener("input", updateSaveBar);
        field.addEventListener("change", updateSaveBar);
    });

    form.addEventListener("reset", () => {
        requestAnimationFrame(updateSaveBar);
    });

    form.addEventListener("submit", () => {
        saveBar.classList.add("is-visible");
    });

    updateSaveBar();
}

function initializeLandingReveal() {
    const revealNodes = Array.from(document.querySelectorAll(".hm-reveal"));

    if (!revealNodes.length || !("IntersectionObserver" in window)) {
        revealNodes.forEach((node) => node.classList.add("is-visible"));
        return;
    }

    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) {
                    return;
                }

                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        },
        {
            threshold: 0.18,
            rootMargin: "0px 0px -8% 0px",
        }
    );

    revealNodes.forEach((node) => {
        if (node.classList.contains("is-visible")) {
            return;
        }

        observer.observe(node);
    });
}

initializeThemeToggle();
initializeSearchShortcut();
initializeSettingsSaveBar();
initializeLandingReveal();

async function parseJsonResponse(response, fallbackMessage) {
    const contentType = response.headers.get("content-type") || "";
    const rawText = await response.text();
    let payload = {};

    if (rawText && contentType.includes("application/json")) {
        try {
            payload = JSON.parse(rawText);
        } catch (error) {
            payload = {};
        }
    }

    if (response.ok) {
        if (contentType.includes("application/json")) {
            return payload;
        }
        throw new Error(fallbackMessage);
    }

    if (payload.error) {
        throw new Error(payload.error);
    }

    if (rawText.trim().startsWith("<!doctype") || rawText.trim().startsWith("<html")) {
        throw new Error("The server returned an HTML page instead of JSON. Please refresh and try again.");
    }

    throw new Error(fallbackMessage);
}

function initializeResumeComparator() {
    const shell = document.querySelector("[data-resume-comparator]");
    if (!shell) {
        return;
    }

    const form = shell.querySelector("[data-resume-comparator-form]");
    const fileInput = form?.querySelector("input[name='resume_file']");
    const dropzone = shell.querySelector("[data-dropzone]");
    const fileName = shell.querySelector("[data-file-name]");
    const submitButton = shell.querySelector("[data-submit-button]");
    const formStatus = shell.querySelector("[data-form-status]");
    const emptyState = shell.querySelector("[data-empty-state]");
    const resultBody = shell.querySelector("[data-result-body]");
    const ring = shell.querySelector("[data-a3-ring]");
    const historyList = shell.querySelector("[data-history-list]");
    const simulationPanel = shell.querySelector("[data-simulation]");
    const explanationSummary = shell.querySelector("[data-explanation-summary]");
    const explanationDetail = shell.querySelector("[data-explanation-detail]");
    const explanationStrengths = shell.querySelector("[data-explanation-strengths]");
    const explanationWeaknesses = shell.querySelector("[data-explanation-weaknesses]");
    const improveButton = document.querySelector("[data-improve-resume-button]");
    const improverOutput = document.querySelector("[data-improver-output]");
    const chatUrl = shell.dataset.chatUrl;
    const improveUrl = shell.dataset.improveUrl;
    const csrfToken = shell.dataset.csrfToken;
    const chatToggleButtons = Array.from(document.querySelectorAll("[data-chat-toggle]"));
    const chatbot = document.querySelector("[data-chatbot]");
    const chatThread = document.querySelector("[data-chat-thread]");
    const chatForm = document.querySelector("[data-chat-form]");

    const setFileName = () => {
        if (!fileInput || !fileName) {
            return;
        }
        fileName.textContent = fileInput.files?.[0]?.name || "No file selected";
    };

    const setLoading = (isLoading) => {
        if (!submitButton) {
            return;
        }
        submitButton.disabled = isLoading;
        submitButton.textContent = isLoading ? "Comparing..." : "Compare";
    };

    const updateText = (selector, value) => {
        const node = shell.querySelector(selector);
        if (node) {
            node.textContent = value;
        }
    };

    const updateBar = (name, value) => {
        const bar = shell.querySelector(`[data-bar='${name}']`);
        if (bar) {
            bar.style.width = `${Math.max(0, Math.min(100, value))}%`;
        }
    };

    const renderList = (containerSelector, items, itemClassName) => {
        const container = shell.querySelector(containerSelector);
        if (!container) {
            return;
        }
        container.innerHTML = "";
        items.forEach((item) => {
            const element = document.createElement(itemClassName === "li" ? "li" : "article");
            if (itemClassName !== "li") {
                element.className = itemClassName;
            }
            element.textContent = item;
            container.appendChild(element);
        });
    };

    const appendHistoryItem = (payload, jobUrl) => {
        if (!historyList) {
            return;
        }

        const emptyCopy = historyList.querySelector(".empty-copy");
        if (emptyCopy) {
            emptyCopy.remove();
        }

        const row = document.createElement("div");
        row.className = "a3-history-item";
        row.innerHTML = `
            <div>
                <strong>A3 Match Engine</strong>
                <p>${jobUrl}</p>
            </div>
            <div class="a3-history-metrics">
                <span>${Math.round(payload.a3_score)} A3</span>
                <span>${Math.round(payload.hiring_probability)}% Hire</span>
                <small>Just now</small>
            </div>
        `;
        historyList.prepend(row);

        const rows = historyList.querySelectorAll(".a3-history-item");
        rows.forEach((item, index) => {
            if (index > 3) {
                item.remove();
            }
        });
    };

    const renderResult = (payload) => {
        emptyState?.setAttribute("hidden", "hidden");
        resultBody?.removeAttribute("hidden");

        if (ring) {
            ring.style.setProperty("--score", payload.a3_score || 0);
        }

        updateText("[data-a3-score]", String(Math.round(payload.a3_score || 0)));
        updateText("[data-hiring-probability]", `${Math.round(payload.hiring_probability || 0)}%`);
        updateText(
            "[data-probability-copy]",
            (payload.hiring_probability || 0) >= 75
                ? "This resume looks highly aligned for the target role."
                : (payload.hiring_probability || 0) >= 55
                    ? "You have a realistic shot, with a few high-leverage improvements."
                    : "The role is reachable, but the engine sees clear areas to strengthen first."
        );
        updateText("[data-alignment]", `${Math.round(payload.alignment || 0)}%`);
        updateText("[data-depth]", `${Math.round(payload.depth || 0)}%`);
        updateText("[data-adaptability]", `${Math.round(payload.adaptability || 0)}%`);
        updateBar("alignment", payload.alignment || 0);
        updateBar("depth", payload.depth || 0);
        updateBar("adaptability", payload.adaptability || 0);

        renderList("[data-skill-gaps]", (payload.skill_gaps || []).slice(0, 6), "li");
        renderList("[data-suggestions]", (payload.suggestions || []).slice(0, 4), "a3-suggestion-card");

        if (payload.simulation?.headline) {
            simulationPanel?.removeAttribute("hidden");
            updateText("[data-simulation-headline]", payload.simulation.headline);
            updateText("[data-simulation-score]", String(Math.round(payload.simulation.projected_a3_score || 0)));
            updateText("[data-simulation-probability]", String(Math.round(payload.simulation.projected_hiring_probability || 0)));
        } else {
            simulationPanel?.setAttribute("hidden", "hidden");
        }

        if (payload.explanation) {
            if (explanationSummary) {
                explanationSummary.textContent = payload.explanation.summary || "";
            }
            if (explanationDetail) {
                explanationDetail.textContent = payload.explanation.detailed || "";
            }
            if (explanationStrengths) {
                explanationStrengths.textContent = (payload.explanation.strengths || []).join(", ") || "Pending analysis";
            }
            if (explanationWeaknesses) {
                explanationWeaknesses.textContent = (payload.explanation.weaknesses || []).join(", ") || "Pending analysis";
            }
        }
    };

    const appendChatBubble = (message, tone = "ai") => {
        if (!chatThread) {
            return;
        }
        const bubble = document.createElement("div");
        bubble.className = `a3-chat-bubble ${tone}`;
        bubble.textContent = message;
        chatThread.appendChild(bubble);
        chatThread.scrollTop = chatThread.scrollHeight;
    };

    if (fileInput) {
        fileInput.addEventListener("change", setFileName);
        setFileName();
    }

    if (dropzone && fileInput) {
        ["dragenter", "dragover"].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.add("is-dragover");
            });
        });

        ["dragleave", "dragend", "drop"].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.remove("is-dragover");
            });
        });

        dropzone.addEventListener("drop", (event) => {
            const files = event.dataTransfer?.files;
            if (!files?.length) {
                return;
            }
            fileInput.files = files;
            setFileName();
        });
    }

    const initialResult = shell.dataset.initialResult ? JSON.parse(shell.dataset.initialResult) : null;
    if (initialResult) {
        renderResult(initialResult);
    }

    chatToggleButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (!chatbot) {
                return;
            }
            const isHidden = chatbot.hasAttribute("hidden");
            if (isHidden) {
                chatbot.removeAttribute("hidden");
            } else {
                chatbot.setAttribute("hidden", "hidden");
            }
        });
    });

    chatForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const input = chatForm.querySelector("input[name='query']");
        const query = input?.value?.trim();
        if (!query || !chatUrl) {
            return;
        }
        appendChatBubble(query, "user");
        input.value = "";
        try {
            const response = await fetch(chatUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({ query }),
            });
            const payload = await parseJsonResponse(response, "AI chat is unavailable.");
            appendChatBubble(payload.answer || "I couldn't generate a response just now.", "ai");
        } catch (error) {
            appendChatBubble(error.message || "AI chat is unavailable.", "ai");
        }
    });

    improveButton?.addEventListener("click", async () => {
        if (!improveUrl || !improverOutput) {
            return;
        }
        improveButton.disabled = true;
        improveButton.textContent = "Improving...";
        try {
            const response = await fetch(improveUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": csrfToken,
                },
            });
            const payload = await parseJsonResponse(response, "Resume improver is unavailable.");
            improverOutput.innerHTML = `
                <strong>Optimized Summary</strong>
                <p>${payload.optimized_summary || ""}</p>
                <strong>Rewrite Notes</strong>
                <p>${(payload.rewrite_notes || []).join(" ")}</p>
                <strong>Project Idea</strong>
                <p>${payload.project_idea || ""}</p>
            `;
            improverOutput.removeAttribute("hidden");
        } catch (error) {
            improverOutput.textContent = error.message || "Resume improver is unavailable.";
            improverOutput.removeAttribute("hidden");
        } finally {
            improveButton.disabled = false;
            improveButton.textContent = "Resume Improver";
        }
    });

    form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!form) {
            return;
        }

        setLoading(true);
        if (formStatus) {
            formStatus.textContent = "Analyzing the role, parsing your resume, and building the A3 score...";
        }

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            const payload = await parseJsonResponse(response, "Comparison failed.");

            renderResult(payload);
            appendHistoryItem(payload, form.elements.job_url.value);
            improverOutput?.setAttribute("hidden", "hidden");
            if (formStatus) {
                formStatus.textContent = "A3 analysis complete. Review the strongest leverage points below.";
            }
        } catch (error) {
            if (formStatus) {
                formStatus.textContent = error.message || "Comparison failed.";
            }
        } finally {
            setLoading(false);
        }
    });
}

initializeResumeComparator();
