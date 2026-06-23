const CACHE_NAME = "pvh-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "Photonostics Alert", body: event.data ? event.data.text() : "" };
  }

  const title   = data.title   || "Photonostics";
  const options = {
    body:     data.body    || "",
    tag:      data.tag     || "pvh-alert",
    renotify: true,
    icon:     "/static/images/icon.png",
    badge:    "/static/images/icon.png",
    data:     { url: "/dashboard" },
    actions:  [
      { action: "view",    title: "View Dashboard" },
      { action: "dismiss", title: "Dismiss" },
    ],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  if (event.action === "dismiss") return;

  const targetUrl = (event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : "/dashboard";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(targetUrl) && "focus" in client) {
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});