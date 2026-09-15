// Service worker mínimo para instalabilidad como PWA: cachea en caliente
// (cache-first) los assets propios de la app (mismo origen), y deja pasar
// sin tocar cualquier request a la API del backend (otro origen) — las
// respuestas normativas siempre deben ir a la red, nunca servirse
// cacheadas.

const CACHE_NAME = "buscador-normatividad-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((claves) =>
        Promise.all(claves.filter((clave) => clave !== CACHE_NAME).map((clave) => caches.delete(clave))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (evento) => {
  const url = new URL(evento.request.url);
  if (evento.request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  evento.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cacheado = await cache.match(evento.request);
      if (cacheado) return cacheado;
      const respuesta = await fetch(evento.request);
      if (respuesta.ok) cache.put(evento.request, respuesta.clone());
      return respuesta;
    }),
  );
});
