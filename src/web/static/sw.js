// Zenic-Flijo Service Worker — PWA offline support (reparado para SPA React)
// ============================================================================
// Fase 1 (sesión 5): REPARADO. Antes cacheaba assets Jinja legacy
// (/static/style.css, /static/editor.js, etc.) que fueron eliminados.
// Ahora cachea los assets del SPA React en /static/spa/* usando estrategias
// modernas (stale-while-revalidate) porque los nombres tienen hash y cambian
// en cada build.
//
// Estrategias de cache:
//   - SPA assets (/static/spa/*): stale-while-revalidate (rápido + actualizado)
//   - PWA icons (/static/icons/*): cache-first (inmutables)
//   - API GET: network-first con fallback a cache (datos frescos, offline ok)
//   - HTML navigations: network-first con fallback a index.html del SPA
//   - POST/PUT/DELETE: siempre network (no se cachean mutaciones)

const VERSION = 'zenic-flijo-v5.0.0';
const STATIC_CACHE = `${VERSION}-static`;
const SPA_CACHE = `${VERSION}-spa`;
const API_CACHE = `${VERSION}-api`;
const IMAGE_CACHE = `${VERSION}-images`;

// Rutas de API cacheables para offline (solo GETs de lectura, no mutaciones)
const CACHEABLE_API_PATTERNS = [
  /^\/api\/dashboard\/stats$/,
  /^\/api\/dashboard\/timeline$/,
  /^\/api\/system\/status$/,
  /^\/api\/system\/backups$/,
  /^\/api\/system\/backup\/auto$/,
  /^\/api\/license\/info$/,
  /^\/api\/airgap\/status$/,
  /^\/api\/airgap\/config$/,
  /^\/api\/partners\/overview$/,
  /^\/api\/partners\/tiers$/,
  /^\/api\/marketplace\/categories$/,
  /^\/api\/marketplace\/connectors$/,
  /^\/api\/orbital\/status$/,
  /^\/api\/compliance\/overview$/,
  /^\/api\/v2\/crm\/stats$/,
  /^\/api\/v2\/inventory\/stats$/,
  /^\/api\/v2\/invoices\/stats$/,
  /^\/api\/v2\/fiscal\/countries$/,
];

// Assets estáticos del SPA para precachear en install (versionados con hash,
// pero el index.html y favicon son estables)
const PRECACHE_URLS = [
  '/static/spa/index.html',
  '/static/spa/favicon.svg',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
];

// ─── Install: precachear assets estables ─────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SPA_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
      .catch((err) => {
        // No fallar el install si algún asset no existe (e.g. en dev sin build)
        console.warn('[SW] precache falló (no bloqueante):', err);
        return self.skipWaiting();
      })
  );
});

// ─── Activate: limpiar caches viejos ─────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys
          .filter((key) => !key.startsWith(VERSION))
          .map((key) => {
            console.log('[SW] eliminando cache viejo:', key);
            return caches.delete(key);
          })
      ))
      .then(() => self.clients.claim())
  );
});

// ─── Fetch: estrategia según tipo de recurso ────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Solo manejar GETs (POST/PUT/DELETE siempre van a network)
  if (request.method !== 'GET') return;

  // Ignorar requests de otros orígenes (CDNs, analytics, etc.)
  if (url.origin !== self.location.origin) return;

  // 1. SPA assets (/static/spa/*): stale-while-revalidate
  if (url.pathname.startsWith('/static/spa/')) {
    event.respondWith(staleWhileRevalidate(request, SPA_CACHE));
    return;
  }

  // 2. PWA icons y manifest (/static/icons/*, /static/manifest.json): cache-first
  if (url.pathname.startsWith('/static/icons/') || url.pathname === '/static/manifest.json') {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // 3. API GETs cacheables: network-first con fallback offline
  if (url.pathname.startsWith('/api/') && CACHEABLE_API_PATTERNS.some((p) => p.test(url.pathname))) {
    event.respondWith(networkFirstWithCacheFallback(request, API_CACHE));
    return;
  }

  // 4. Navegación HTML (documentos): network-first, fallback a SPA index.html
  if (request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const clone = response.clone();
          caches.open(SPA_CACHE).then((cache) => cache.put(request, clone));
          return response;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match('/static/spa/index.html')))
    );
    return;
  }

  // 5. Imágenes: cache-first con fallback network
  if (request.destination === 'image') {
    event.respondWith(cacheFirst(request, IMAGE_CACHE));
    return;
  }
});

// ─── Estrategias de cache ────────────────────────────────────────────────

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    return new Response('', { status: 504, statusText: 'Gateway Timeout' });
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached); // si network falla y hay cache, usar cache
  return cached || fetchPromise;
}

async function networkFirstWithCacheFallback(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ error: 'offline', message: 'Sin conexión. Datos no disponibles offline.' }),
      { headers: { 'Content-Type': 'application/json' }, status: 503 }
    );
  }
}

// ─── Push notifications ──────────────────────────────────────────────────
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'Zenic Flujo';
  const options = {
    body: data.body || 'Nueva notificación',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      deepLink: data.deep_link || '/app/dashboard',
      category: data.category || 'system',
    },
    actions: data.actions || [],
    tag: data.notification_id || 'zenic-notification',
    requireInteraction: data.priority === 'high',
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// ─── Notification click: abrir deep link ─────────────────────────────────
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const deepLink = event.notification.data?.deepLink || '/app/dashboard';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Si ya hay una ventana abierta, enfocarla y navegar
        for (const client of clientList) {
          if (client.url.includes(self.location.origin)) {
            client.focus();
            if ('navigate' in client) client.navigate(deepLink);
            return;
          }
        }
        // Si no, abrir nueva ventana
        return clients.openWindow(deepLink);
      })
  );
});

// ─── Message: permitir forzar update desde la app ────────────────────────
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
