{% load static %}
const CACHE_NAME = "home-sweet-home-static-v5";
const STATIC_ASSETS = [
    "{% static 'css/app.css' %}?v=5",
    "{% static 'js/app.js' %}?v=5",
    "{% static 'manifest.webmanifest' %}",
    "{% static 'icons/favicon.ico' %}",
    "{% static 'icons/favicon-32.png' %}",
    "{% static 'icons/apple-touch-icon.png' %}",
    "{% static 'icons/icon-192.png' %}",
    "{% static 'icons/icon-512.png' %}"
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
