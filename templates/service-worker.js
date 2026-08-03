{% load static %}
const CACHE_NAME = "home-sweet-home-static-v16";
const STATIC_ASSETS = [
    "{% static 'css/app.css' %}?v=16",
    "{% static 'js/app.js' %}?v=7",
    "{% static 'js/ai-assistant.js' %}?v=1",
    "{% static 'manifest.webmanifest' %}",
    "{% static 'icons/favicon.ico' %}",
    "{% static 'icons/favicon-32.png' %}",
    "{% static 'icons/apple-touch-icon.png' %}",
    "{% static 'icons/icon-192.png' %}",
    "{% static 'icons/icon-512.png' %}",
    "{% static 'icons/albert-heijn.svg' %}",
    "{% static 'icons/jumbo.png' %}"
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(CACHE_NAME)
            .then((cache) => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((names) =>
                Promise.all(
                    names
                        .filter(
                            (name) =>
                                name.startsWith("home-sweet-home-static-") &&
                                name !== CACHE_NAME
                        )
                        .map((name) => caches.delete(name))
                )
            )
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") return;

    const requestUrl = new URL(event.request.url);
    const staticPaths = STATIC_ASSETS.map(
        (asset) => new URL(asset, self.location.origin).pathname
    );
    if (
        requestUrl.origin !== self.location.origin ||
        !staticPaths.includes(requestUrl.pathname)
    ) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then((networkResponse) => {
                if (networkResponse.ok) {
                    const copy = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                }
                return networkResponse;
            })
            .catch(() => caches.match(event.request))
    );
});

self.addEventListener("push", (event) => {
    let payload = {};
    try {
        payload = event.data ? event.data.json() : {};
    } catch {
        payload = {};
    }
    if (!payload || typeof payload !== "object") payload = {};

    const title =
        typeof payload.title === "string" && payload.title.trim()
            ? payload.title.slice(0, 120)
            : "Home Sweet Home";
    const body =
        typeof payload.body === "string" && payload.body.trim()
            ? payload.body.slice(0, 300)
            : "There is an update from your household.";
    const url = sameOriginRelativeUrl(payload.url);
    const tag =
        typeof payload.tag === "string" && payload.tag.trim()
            ? payload.tag.slice(0, 120)
            : "home-sweet-home-update";

    event.waitUntil(
        self.registration.showNotification(title, {
            body,
            icon: "{% static 'icons/icon-192.png' %}",
            tag,
            data: { url },
        })
    );
});

function sameOriginRelativeUrl(value) {
    if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
        return "/";
    }
    try {
        const parsed = new URL(value, self.location.origin);
        if (parsed.origin !== self.location.origin) return "/";
        return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    } catch {
        return "/";
    }
}

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const targetUrl = sameOriginRelativeUrl(event.notification.data?.url);

    event.waitUntil(
        self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(
            async (windowClients) => {
                for (const client of windowClients) {
                    const clientUrl = new URL(client.url);
                    if (clientUrl.origin !== self.location.origin) continue;
                    if (clientUrl.pathname + clientUrl.search + clientUrl.hash !== targetUrl) {
                        await client.navigate(targetUrl);
                    }
                    return client.focus();
                }
                return self.clients.openWindow(targetUrl);
            }
        )
    );
});
