const globalSearchInput = document.getElementById("candidateGlobalSearch");

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

initializeSearchShortcut();
initializeSettingsSaveBar();
initializeLandingReveal();
