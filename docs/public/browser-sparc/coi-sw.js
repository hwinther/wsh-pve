// Cross-origin isolation for the Browser SPARC page on a host that can't set response headers
// (GitHub Pages). QEMU's WebAssembly build runs its threads on a SharedArrayBuffer, which browsers
// only allow in a cross-origin isolated page: one served with
//   Cross-Origin-Opener-Policy: same-origin
//   Cross-Origin-Embedder-Policy: require-corp
// This service worker adds both headers to every response within its scope (the page's directory),
// so after the first load (which registers it and reloads once) the page is isolated. The page only
// loads its own files, so require-corp needs no CORP headers from elsewhere.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const request = event.request;
  // A request Chrome makes for devtools; fetch() refuses it outside same-origin mode.
  if (request.cache === "only-if-cached" && request.mode !== "same-origin") return;
  event.respondWith(
    fetch(request).then((response) => {
      if (response.status === 0) return response; // opaque: headers can't be changed
      const headers = new Headers(response.headers);
      headers.set("Cross-Origin-Opener-Policy", "same-origin");
      headers.set("Cross-Origin-Embedder-Policy", "require-corp");
      headers.set("Cross-Origin-Resource-Policy", "same-origin");
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    }),
  );
});
