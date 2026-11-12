# iPod Cloudflare Worker (experimental)

This Worker is a server-side relay for authorized YTMP3 audio downloads. It is **not deployed** by committing these files.

## Deploy
1. In Cloudflare Workers & Pages, create a Worker connected to this GitHub repository, or deploy using Wrangler.
2. From the `worker` directory run `npx wrangler deploy` with your Cloudflare account authorized.
3. Set a long random Worker secret: `npx wrangler secret put DOWNLOAD_SIGNING_KEY`.
4. Copy the resulting `https://ipod-audio-relay.<subdomain>.workers.dev` URL into the frontend configuration (not yet wired).

## Routes
- `POST /convert` with JSON `{"videoId":"11-character-ID"}` requests conversion and returns a signed `downloadPath`.
- `POST /audio?url=...&token=...` relays audio bytes; the frontend stores the resulting Blob in IndexedDB.

## Important limitations
- Upstream API access and schema are **not verified**. YTMP3 might reject Cloudflare traffic or disallow server relays.
- CORS is restricted to `https://yartproductions.github.io` (not an authentication mechanism).
- This is an experimental personal-use backend; no rate limiting or abuse protection is implemented. **Do not expose it publicly until those controls are added.**
- Cloudflare Worker runtime and transfer limits apply. iOS browser storage may be evicted.
- Download only content for which you have permission.
