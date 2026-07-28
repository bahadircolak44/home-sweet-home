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

    const urlBase64ToUint8Array = (value) => {
        const padding = "=".repeat((4 - (value.length % 4)) % 4);
        const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
        const rawData = window.atob(base64);
        return Uint8Array.from(rawData, (character) => character.charCodeAt(0));
    };

    const csrfToken = () => {
        const prefix = "csrftoken=";
        return document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith(prefix))
            ?.slice(prefix.length);
    };

    const setupPushNotifications = () => {
        const panel = document.querySelector("[data-notification-settings]");
        if (!panel) return;

        const status = panel.querySelector("[data-notification-status]");
        const enableButton = panel.querySelector("[data-enable-notifications]");
        const testButton = panel.querySelector("[data-test-notification]");
        const disableButton = panel.querySelector("[data-disable-notifications]");
        const buttons = [enableButton, testButton, disableButton];
        const supportsPush =
            "serviceWorker" in navigator &&
            "PushManager" in window &&
            "Notification" in window;
        const isIos =
            /iphone|ipad|ipod/i.test(navigator.userAgent) ||
            (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
        const publicKey = panel.dataset.vapidPublicKey || "";
        let registration = null;
        let subscription = null;

        const setStatus = (message) => {
            status.textContent = message;
        };
        const show = (button, visible) => {
            button.hidden = !visible;
        };
        const setBusy = (busy) => {
            buttons.forEach((button) => {
                button.disabled = busy;
            });
        };
        const showActions = ({ enable = false, test = false, disable = false }) => {
            show(enableButton, enable);
            show(testButton, test);
            show(disableButton, disable);
        };
        const serviceWorkerReady = () =>
            Promise.race([
                navigator.serviceWorker.ready,
                new Promise((_, reject) => {
                    window.setTimeout(
                        () => reject(new Error("Service worker was not ready.")),
                        10000
                    );
                }),
            ]);
        const postJson = async (url, data) => {
            const token = csrfToken();
            if (!token) throw new Error("Missing CSRF token.");
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                    "X-CSRFToken": token,
                },
                body: JSON.stringify(data),
            });
            const responseData = await response.json().catch(() => ({}));
            if (!response.ok || !responseData.success) {
                throw new Error("Notification request failed.");
            }
            return responseData;
        };

        const syncState = async () => {
            if (!supportsPush) {
                setStatus("Notifications are not supported by this browser.");
                showActions({});
                return;
            }
            if (isIos && !isStandalone()) {
                setStatus(
                    "Install Home Sweet Home on your Home Screen before enabling notifications."
                );
                showActions({});
                return;
            }
            if (Notification.permission === "denied") {
                setStatus(
                    "Notifications are blocked. Enable them from your browser or device settings."
                );
                showActions({});
                return;
            }
            if (!publicKey) {
                setStatus("Notifications are not configured for this site.");
                showActions({});
                return;
            }

            try {
                registration = await serviceWorkerReady();
                subscription = await registration.pushManager.getSubscription();
            } catch {
                setStatus("Notifications could not be prepared on this device. Please try again.");
                showActions({});
                return;
            }

            if (Notification.permission === "granted" && subscription) {
                setStatus("Notifications are enabled on this device.");
                showActions({ test: true, disable: true });
                return;
            }

            setStatus("Enable notifications to receive grocery list updates on this device.");
            showActions({ enable: true });
        };

        enableButton.addEventListener("click", async () => {
            setBusy(true);
            try {
                const permission = await Notification.requestPermission();
                if (permission !== "granted") {
                    await syncState();
                    return;
                }
                registration = registration || (await serviceWorkerReady());
                subscription =
                    (await registration.pushManager.getSubscription()) ||
                    (await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(publicKey),
                    }));
                await postJson(panel.dataset.subscribeUrl, subscription.toJSON());
                setStatus("Notifications are enabled on this device.");
                showActions({ test: true, disable: true });
            } catch {
                setStatus("Notifications could not be enabled. Please try again.");
            } finally {
                setBusy(false);
            }
        });

        disableButton.addEventListener("click", async () => {
            setBusy(true);
            try {
                registration = registration || (await serviceWorkerReady());
                subscription = subscription || (await registration.pushManager.getSubscription());
                if (subscription) {
                    await postJson(panel.dataset.unsubscribeUrl, {
                        endpoint: subscription.endpoint,
                    });
                    await subscription.unsubscribe();
                    subscription = null;
                }
                setStatus("Notifications are disabled on this device.");
                showActions({ enable: true });
            } catch {
                setStatus("Notifications could not be disabled. Please try again.");
            } finally {
                setBusy(false);
            }
        });

        testButton.addEventListener("click", async () => {
            setBusy(true);
            try {
                registration = registration || (await serviceWorkerReady());
                subscription = subscription || (await registration.pushManager.getSubscription());
                if (!subscription) throw new Error("Missing subscription.");
                await postJson(panel.dataset.testUrl, { endpoint: subscription.endpoint });
                setStatus("Test notification sent to this device.");
                showActions({ test: true, disable: true });
            } catch {
                setStatus("The test notification could not be sent. Please try again.");
            } finally {
                setBusy(false);
            }
        });

        syncState();
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
        setupPushNotifications();
    });

    document.body.addEventListener("htmx:beforeSwap", (event) => {
        if (event.detail.xhr.status === 422) {
            event.detail.shouldSwap = true;
            event.detail.isError = false;
        }
    });

    document.body.addEventListener("htmx:afterSwap", (event) => {
        const trigger = event.detail.requestConfig?.elt;
        if (trigger?.closest?.("[data-add-item-form]")) {
            document
                .querySelector("#list-live-region [data-add-item-input]")
                ?.focus({ preventScroll: true });
        }
        if (trigger?.closest?.("[data-add-chore-task-form]")) {
            document
                .querySelector("#session-live-region [data-add-chore-task-input]")
                ?.focus({ preventScroll: true });
        }
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
