// Zenic-Flijo Service Worker — PWA offline support
// Enables the app to work offline on Android/iOS without Play Store

const CACHE_NAME = 'zenic-flijo-v2.1.0';
const STATIC_CACHE = 'zenic-static-v2.1.0';
const API_CACHE = 'zenic-api-v2.1.0';
const IMAGE_CACHE = 'zenic-images-v2.1.0';

// Static assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/static/css/style.css',
  '/static/js/editor.js',
  '/static/js/orbital-visualizer.js',
  '/static/chart.umd.min.js',
];

// API routes to cache for offline access
const CACHEABLE_API = [
  '/api/v2/mobile/dashboard',
  '/api/v2/mobile/config',
  '/api/v2/health',
];

// Install: cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME && key !== STATIC_CACHE && key !== API_CACHE)
          .map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: network-first for API, cache-first for static
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API requests: network first, fall back to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      caches.open(API_CACHE).then((cache) => {
        return fetch(event.request)
          .then((response) => {
            // Cache successful GET responses for offline use
            if (event.request.method === 'GET' && response.ok) {
              const isCacheable = CACHEABLE_API.some((path) =>
                url.pathname.includes(path)
              );
              if (isCacheable) {
                cache.put(event.request, response.clone());
              }
            }
            return response;
          })
          .catch(() => {
            // Network failed, try cache
            return cache.match(event.request).then((cached) => {
              if (cached) return cached;
              // Return offline response for API calls
              return new Response(
                JSON.stringify({ error: 'offline', message: 'Sin conexión. Datos en caché.' }),
                { headers: { 'Content-Type': 'application/json' }, status: 503 }
              );
            });
          });
      })
    );
    return;
  }

  // Static assets: cache first, network fallback
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages: network first, cache fallback
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then((cached) => cached || caches.match('/')))
  );
});

// Push notification handler
self.addEventListener('push', (event) => {
  const data = event.json ? event.json() : {};
  const title = data.title || 'Zenic-Flijo';
  const options = {
    body: data.body || 'Nueva notificación',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      deepLink: data.deep_link || '/',
      category: data.category || 'system',
    },
    actions: data.actions || [],
    tag: data.notification_id || 'zenic-notification',
    requireInteraction: data.priority === 'high',
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// Notification click handler — deep link into the app
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const deepLink = event.notification.data?.deepLink || '/';
  const action = event.action;

  if (action === 'approve' || action === 'reject' || action === 'retry') {
    // Handle quick actions from notification
    event.waitUntil(
      fetch('/api/v2/mobile/notification/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          notification_id: event.notification.tag,
          action: action,
        }),
      }).then(() => self.clients.openWindow(deepLink))
    );
  } else {
    event.waitUntil(self.clients.openWindow(deepLink));
  }
});

// Background sync for offline operations
self.addEventListener('sync', (event) => {
  if (event.tag === 'zenic-sync') {
    event.waitUntil(
      fetch('/api/v2/mobile/sync/push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sync_type: 'background' }),
      })
    );
  }
});

// Share target handler (receive shared files/text from other Android apps)
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SHARE_TARGET') {
    // Process shared content from Android share sheet
    const { title, text, url, files } = event.data;
    // Route to appropriate workflow or NLU processing
  }
});
