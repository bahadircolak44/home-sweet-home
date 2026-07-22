(() => {
    let deferredInstallPrompt = null;

    const isStandalone = () =>
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true;

    const installButton = () => document.querySelector("[data-install-app]");

    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        deferredInstallPrompt = event;
        const button = installButton();
        if (button && !isStandalone()) button.hidden = false;
    });

    window.addEventListener("appinstalled", () => {
        deferredInstallPrompt = null;
        const button = installButton();
        if (button) button.hidden = true;
    });

    document.addEventListener("click", async (event) => {
        const detailsButton = event.target.closest("[data-item-details-toggle]");
        if (detailsButton) {
            const form = detailsButton.closest("form");
            const details = form.querySelector("[data-item-details]");
            const expanded = detailsButton.getAttribute("aria-expanded") === "true";
            detailsButton.setAttribute("aria-expanded", String(!expanded));
            details.hidden = expanded;
            if (!expanded) details.querySelector("textarea")?.focus();
            return;
        }

        const requestedInstall = event.target.closest("[data-install-app]");
        if (requestedInstall && deferredInstallPrompt) {
            requestedInstall.hidden = true;
            deferredInstallPrompt.prompt();
            const choice = await deferredInstallPrompt.userChoice;
            deferredInstallPrompt = null;
            if (choice.outcome !== "accepted") requestedInstall.hidden = false;
            return;
        }

        const iosHelpButton = event.target.closest("[data-ios-install-help]");
        if (iosHelpButton) {
            const instructions = document.querySelector(
                "[data-ios-install-instructions]"
            );
            instructions.hidden = !instructions.hidden;
        }
    });

    const httpUrlsFromClipboard = (clipboardData) => {
        const urls = [];
        const addUrl = (candidate) => {
            const value = candidate.trim();
            if (/^https?:\/\/\S+$/i.test(value) && !urls.includes(value)) {
                urls.push(value);
            }
        };

        clipboardData
            .getData("text/uri-list")
            .split(/\r?\n/)
            .filter((line) => line && !line.startsWith("#"))
            .forEach(addUrl);

        const html = clipboardData.getData("text/html");
        if (html) {
            const clipboardDocument = new DOMParser().parseFromString(
                html,
                "text/html"
            );
            clipboardDocument
                .querySelectorAll("a[href]")
                .forEach((link) => addUrl(link.getAttribute("href") || ""));
        }

        return urls;
    };

    document.addEventListener("paste", (event) => {
        const description = event.target.closest?.("[data-description-input]");
        if (!description || !event.clipboardData) return;

        const plainText = event.clipboardData
            .getData("text/plain")
            .replace(/\r\n?/g, "\n");
        const missingUrls = httpUrlsFromClipboard(event.clipboardData).filter(
            (url) => !plainText.includes(url)
        );
        const clipboardText = [plainText, ...missingUrls]
            .filter(Boolean)
            .join("\n");
        if (!clipboardText) return;

        const selectionStart = description.selectionStart ?? description.value.length;
        const selectionEnd = description.selectionEnd ?? selectionStart;
        const retainedLength =
            description.value.length - (selectionEnd - selectionStart);
        const availableLength =
            description.maxLength > 0
                ? Math.max(description.maxLength - retainedLength, 0)
                : clipboardText.length;

        event.preventDefault();
        description.setRangeText(
            clipboardText.slice(0, availableLength),
            selectionStart,
            selectionEnd,
            "end"
        );
        description.dispatchEvent(new Event("input", { bubbles: true }));
    });

    document.addEventListener("DOMContentLoaded", () => {
        const isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
        const iosHelpButton = document.querySelector("[data-ios-install-help]");
        if (isIos && !isStandalone() && iosHelpButton) iosHelpButton.hidden = false;
    });

    document.body.addEventListener("htmx:beforeSwap", (event) => {
        if (event.detail.xhr.status === 422) {
            event.detail.shouldSwap = true;
            event.detail.isError = false;
        }
    });

    document.body.addEventListener("htmx:afterSwap", (event) => {
        const trigger = event.detail.requestConfig?.elt;
        if (!trigger?.closest?.("[data-add-item-form]")) return;
        document
            .querySelector("#list-live-region [data-add-item-input]")
            ?.focus({ preventScroll: true });
    });

    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            const serviceWorkerUrl = document.body.dataset.serviceWorkerUrl;
            navigator.serviceWorker
                .register(serviceWorkerUrl, { scope: "/" })
                .catch(() => {});
        });
    }
})();
