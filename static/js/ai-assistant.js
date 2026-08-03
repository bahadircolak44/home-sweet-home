(() => {
    const csrfToken = () => {
        const prefix = "csrftoken=";
        return document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith(prefix))
            ?.slice(prefix.length);
    };

    const requestId = () => {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
            const random = Math.floor(Math.random() * 16);
            const value = character === "x" ? random : (random & 0x3) | 0x8;
            return value.toString(16);
        });
    };

    const recordingMimeType = () => {
        if (!window.MediaRecorder) return "";
        return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
            .find((type) => MediaRecorder.isTypeSupported(type)) || "";
    };

    const startAssistant = () => {
        const panel = document.querySelector("[data-ai-assistant]");
        if (!panel) return;

        const form = panel.querySelector("[data-ai-assistant-text-form]");
        const input = panel.querySelector("[data-ai-assistant-input]");
        const sendButton = panel.querySelector("[data-ai-assistant-send]");
        const recordButton = panel.querySelector("[data-ai-assistant-record]");
        const stopButton = panel.querySelector("[data-ai-assistant-stop]");
        const status = panel.querySelector("[data-ai-assistant-status]");
        const preview = panel.querySelector("[data-ai-assistant-preview]");
        const transcript = panel.querySelector("[data-ai-assistant-transcript]");
        const summary = panel.querySelector("[data-ai-assistant-summary]");
        const confirmButton = panel.querySelector("[data-ai-assistant-confirm]");
        const cancelButton = panel.querySelector("[data-ai-assistant-cancel]");
        const maxMilliseconds = Math.max(1, Number(panel.dataset.maxSeconds || 20)) * 1000;
        let busy = false;
        let recorder = null;
        let mediaStream = null;
        let stopTimer = null;
        let activeCommand = null;

        const setStatus = (message) => {
            status.textContent = message || "";
        };
        const setBusy = (value) => {
            busy = value;
            sendButton.disabled = value;
            recordButton.disabled = value;
            confirmButton.disabled = value;
            cancelButton.disabled = value;
        };
        const releaseStream = () => {
            if (stopTimer) window.clearTimeout(stopTimer);
            stopTimer = null;
            mediaStream?.getTracks().forEach((track) => track.stop());
            mediaStream = null;
        };
        const hidePreview = () => {
            preview.hidden = true;
            activeCommand = null;
        };
        const showPreview = (data) => {
            activeCommand = data;
            transcript.textContent = data.transcript || "";
            summary.textContent = data.summary || "";
            preview.hidden = false;
        };
        const showResult = (data) => {
            hidePreview();
            status.replaceChildren();
            const message = document.createTextNode(data.message || "Added.");
            status.append(message);
            if (typeof data.result_url === "string" && data.result_url.startsWith("/") && !data.result_url.startsWith("//")) {
                const link = document.createElement("a");
                link.href = data.result_url;
                link.className = "ai-assistant-status__link";
                link.textContent = data.result_label || "Open result";
                status.append(document.createTextNode(" "));
                status.append(link);
            }
        };
        const post = async (url, body) => {
            const token = csrfToken();
            if (!token) throw new Error("Missing CSRF token.");
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: { Accept: "application/json", "X-CSRFToken": token },
                body,
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(data.message || "The command could not be completed.");
            }
            return data;
        };
        const handleInterpretation = (data) => {
            if (data.status === "needs_confirmation") {
                setStatus("");
                showPreview(data);
                return;
            }
            hidePreview();
            if (data.status === "unresolved") {
                const candidates = Array.isArray(data.candidates) && data.candidates.length
                    ? ` Candidates: ${data.candidates.join(", ")}.`
                    : "";
                setStatus(`${data.message || "Please try again."}${candidates}`);
                return;
            }
            setStatus(data.message || "I could not understand that command right now. Nothing was added.");
        };
        const submitText = async () => {
            const command = input.value.trim();
            if (!command) {
                setStatus("Enter a command first.");
                input.focus();
                return;
            }
            setBusy(true);
            setStatus("Understanding…");
            hidePreview();
            try {
                const body = new FormData();
                body.append("command", command);
                body.append("request_id", requestId());
                handleInterpretation(await post(panel.dataset.textUrl, body));
            } catch (error) {
                setStatus(error.message || "I could not understand that command right now. Nothing was added.");
            } finally {
                setBusy(false);
            }
        };
        const submitAudio = async (blob) => {
            setBusy(true);
            setStatus("Transcribing…");
            hidePreview();
            try {
                const extension = blob.type.includes("mp4") ? "m4a" : "webm";
                const body = new FormData();
                body.append("audio", blob, `quick-add.${extension}`);
                body.append("request_id", requestId());
                const data = await post(panel.dataset.audioUrl, body);
                if (data.status === "needs_confirmation") setStatus("Understanding…");
                handleInterpretation(data);
            } catch (error) {
                setStatus(error.message || "The recording could not be understood. Nothing was added.");
            } finally {
                releaseStream();
                setBusy(false);
            }
        };
        const stopRecording = () => {
            if (!recorder || recorder.state === "inactive") return;
            setStatus("Transcribing…");
            stopButton.hidden = true;
            recorder.stop();
        };

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            if (!busy) submitText();
        });
        recordButton.addEventListener("click", async () => {
            if (busy || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
                setStatus("Microphone recording is not supported by this browser. You can still type a command.");
                return;
            }
            try {
                mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const mimeType = recordingMimeType();
                recorder = mimeType ? new MediaRecorder(mediaStream, { mimeType }) : new MediaRecorder(mediaStream);
                const chunks = [];
                recorder.addEventListener("dataavailable", (event) => {
                    if (event.data.size) chunks.push(event.data);
                });
                recorder.addEventListener("stop", () => {
                    const audio = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
                    recorder = null;
                    submitAudio(audio);
                }, { once: true });
                recorder.start();
                recordButton.hidden = true;
                stopButton.hidden = false;
                setStatus("Listening…");
                stopTimer = window.setTimeout(stopRecording, maxMilliseconds);
            } catch {
                releaseStream();
                setStatus("Microphone permission was not granted. You can still type a command.");
            }
        });
        stopButton.addEventListener("click", stopRecording);
        confirmButton.addEventListener("click", async () => {
            if (!activeCommand || busy) return;
            setBusy(true);
            setStatus("Adding…");
            try {
                showResult(await post(activeCommand.confirm_url, new FormData()));
            } catch (error) {
                setStatus(error.message || "Nothing was added. Please submit the command again.");
            } finally {
                setBusy(false);
            }
        });
        cancelButton.addEventListener("click", async () => {
            if (!activeCommand || busy) return;
            setBusy(true);
            try {
                const data = await post(activeCommand.cancel_url, new FormData());
                hidePreview();
                setStatus(data.message || "Nothing was added.");
            } catch (error) {
                setStatus(error.message || "The proposal could not be cancelled.");
            } finally {
                setBusy(false);
            }
        });
        window.addEventListener("pagehide", releaseStream);
    };

    document.addEventListener("DOMContentLoaded", startAssistant);
})();
