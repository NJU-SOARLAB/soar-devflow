/* Read-only reverse proxy for safe documentation screenshot capture.
 *
 * Serves optional local static frontend files while forwarding GET/HEAD requests
 * to a running upstream service. All mutating requests (POST/PUT/PATCH/DELETE)
 * are blocked locally unless explicitly accepted by allowWrite(pathname, jsonBody).
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.json': 'application/json; charset=utf-8',
};

export async function startReadonlyPreview(upstreamUrl, { staticDir = '', routes = {}, allowWrite = null } = {}) {
  const upstream = new URL(upstreamUrl);
  const resolvedStatic = staticDir ? path.resolve(staticDir) : '';
  const blocked = [];
  const forwarded = [];

  const rejectWrite = (req, res, pathname) => {
    blocked.push(`${req.method} ${pathname}`);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{"ok":false,"preview":"read-only"}');
  };

  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;

    if (req.method !== 'GET' && req.method !== 'HEAD') {
      if (!allowWrite) {
        req.resume();
        rejectWrite(req, res, pathname);
        return;
      }
      const chunks = [];
      req.on('data', d => chunks.push(d));
      req.on('end', () => {
        const body = Buffer.concat(chunks);
        let parsed = null;
        try { parsed = JSON.parse(body.toString('utf8')); } catch {}
        if (!allowWrite(pathname, parsed)) {
          rejectWrite(req, res, pathname);
          return;
        }
        forwarded.push(`${req.method} ${pathname}`);
        const proxy = http.request(
          { host: upstream.hostname, port: upstream.port, path: req.url, method: req.method, headers: { ...req.headers, host: upstream.host, 'content-length': body.length } },
          ur => { res.writeHead(ur.statusCode, ur.headers); ur.pipe(res); }
        );
        proxy.on('error', e => { res.writeHead(502); res.end(String(e)); });
        proxy.end(body);
      });
      return;
    }

    if (resolvedStatic) {
      const name = routes[pathname] || pathname.slice(1);
      const file = path.resolve(resolvedStatic, name);
      if (name && file.startsWith(resolvedStatic + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) {
        res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
        fs.createReadStream(file).pipe(res);
        return;
      }
    }

    const proxy = http.request(
      { host: upstream.hostname, port: upstream.port, path: req.url, method: req.method, headers: { ...req.headers, host: upstream.host } },
      ur => { res.writeHead(ur.statusCode, ur.headers); ur.pipe(res); }
    );
    proxy.on('error', e => { res.writeHead(502); res.end(String(e)); });
    req.on('close', () => proxy.destroy());
    proxy.end();
  });

  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return {
    base: `http://127.0.0.1:${server.address().port}`,
    blocked,
    forwarded,
    close: () => server.close(),
  };
}

export async function launchBrowser() {
  const { chromium } = await import(process.env.SOAR_DEVFLOW_PLAYWRIGHT || 'playwright');
  return chromium.launch({
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
  });
}
