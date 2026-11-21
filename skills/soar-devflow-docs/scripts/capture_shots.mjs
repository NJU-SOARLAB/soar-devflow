#!/usr/bin/env node
/* Reproducible declarative documentation screenshots with numbered callout overlays.
 *
 * Reads shot manifests (*.json) configured in .soar-devflow/docs.json and renders
 * annotated PNGs into the site's public/shots/ directory through a read-only proxy.
 *
 * Usage:
 *   node capture_shots.mjs [--config .soar-devflow/docs.json] [--upstream URL]
 *                          [--only id1,id2] [--list] [--hook ./custom-hook.mjs] [--allow-writes]
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { startReadonlyPreview, launchBrowser } from './readonly_preview.mjs';

const args = process.argv.slice(2);
const opt = name => {
  const idx = args.indexOf(name);
  return idx >= 0 ? args[idx + 1] : undefined;
};

function discoverConfig(explicit) {
  if (explicit) return path.resolve(explicit);
  let cur = process.cwd();
  while (true) {
    for (const rel of ['.soar-devflow/docs.json', 'docs/site/docs.config.json', 'site/docs.config.json']) {
      const candidate = path.join(cur, rel);
      if (fs.existsSync(candidate)) return candidate;
    }
    const parent = path.dirname(cur);
    if (parent === cur) throw new Error('No docs.json found. Pass --config PATH.');
    cur = parent;
  }
}

const configPath = discoverConfig(opt('--config'));
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
const repoRoot = path.basename(path.dirname(configPath)) === '.soar-devflow'
  ? path.dirname(path.dirname(configPath))
  : path.dirname(configPath);
const shotCfg = config.shots || {};

const manifestDir = path.resolve(repoRoot, shotCfg.manifest_dir || path.join(config.site_dir, 'shots'));
const outDir = path.resolve(repoRoot, shotCfg.output_dir || path.join(config.site_dir, 'public/shots'));
const upstreamUrl = opt('--upstream') || process.env.SOAR_DEVFLOW_SHOTS_UPSTREAM || shotCfg.upstream_url || 'http://127.0.0.1:5173';
const staticDir = shotCfg.static_dir ? path.resolve(repoRoot, shotCfg.static_dir) : '';
const only = opt('--only')?.split(',').filter(Boolean);
const allowWrites = args.includes('--allow-writes');
const hookPath = opt('--hook') || (shotCfg.hook ? path.resolve(repoRoot, shotCfg.hook) : null);
const hook = hookPath ? await import(pathToFileURL(path.resolve(hookPath)).href) : {};

const entries = fs.existsSync(manifestDir)
  ? fs.readdirSync(manifestDir).filter(f => f.endsWith('.json')).sort()
      .flatMap(file => JSON.parse(fs.readFileSync(path.join(manifestDir, file), 'utf8')).map(e => ({ ...e, file })))
  : [];

const ids = new Map();
for (const e of entries) {
  if (!/^[a-z0-9][a-z0-9-]*$/.test(e.id || '')) throw new Error(`Invalid shot id in ${e.file}: ${e.id}`);
  if (ids.has(e.id)) throw new Error(`Duplicate shot id ${e.id} in ${e.file} and ${ids.get(e.id)}`);
  ids.set(e.id, e.file);
}

if (args.includes('--list')) {
  for (const e of entries) console.log(e.id, e.page || '/', e.file);
  process.exit(0);
}

const selected = entries.filter(e => !only || only.includes(e.id));
if (only) {
  for (const id of only) if (!ids.has(id)) throw new Error('Unknown shot id: ' + id);
}

let activeShot = null;
const preview = await startReadonlyPreview(upstreamUrl, {
  staticDir,
  routes: shotCfg.routes || {},
  allowWrite: allowWrites && hook.allowWrite ? (p, body) => hook.allowWrite(p, body, activeShot) : null,
});

const browser = await launchBrowser();
fs.mkdirSync(outDir, { recursive: true });
const report = [];

for (const e of selected) {
  if ((e.allowWrites || []).length && !allowWrites) {
    report.push({ id: e.id, ok: true, skipped: 'needs --allow-writes' });
    console.log('SKIP', e.id, '(needs --allow-writes)');
    continue;
  }
  activeShot = e;
  const [width, height] = e.viewport || [1440, 900];
  const theme = e.theme || 'dark';
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: e.scale || 1, colorScheme: theme });
  const themeKey = shotCfg.theme_storage_key || '';
  await ctx.addInitScript(([tk, t, storage]) => {
    try {
      if (tk) localStorage.setItem(tk, t);
      for (const [k, v] of Object.entries(storage)) localStorage.setItem(k, v);
    } catch {}
  }, [themeKey, theme, e.storage || {}]);

  if (hook.beforePage) await hook.beforePage(ctx, e, { config, upstreamUrl });

  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', err => errors.push(err.message));

  try {
    await page.goto(preview.base + (e.page || '/'), { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(e.wait ?? 1500);
    if (hook.afterGoto) await hook.afterGoto(page, e, { config, upstreamUrl });
    if (e.setup) {
      await page.evaluate(`(async()=>{${e.setup}\n})()`);
      await page.waitForTimeout(e.settle ?? 600);
    }
    if (hook.beforeAnnotate) await hook.beforeAnnotate(page, e, { config, upstreamUrl });

    if (e.annotate?.length) {
      await page.evaluate(marks => {
        const layers = new Map();
        const layerFor = el => {
          const top = el.closest('dialog[open],:popover-open') || document.body;
          if (!layers.has(top)) {
            const layer = document.createElement('div');
            layer.style.cssText = (top === document.body ? 'position:absolute' : 'position:fixed')
              + ';left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none';
            top.append(layer);
            layers.set(top, layer);
          }
          return [layers.get(top), top === document.body];
        };
        for (const { selector, label, badge: side } of marks) {
          const el = document.querySelector(selector);
          if (!el) throw new Error('Annotation target missing: ' + selector);
          const r = el.getBoundingClientRect();
          const [layer, inPage] = layerFor(el);
          const x = r.left + (inPage ? scrollX : 0);
          const y = r.top + (inPage ? scrollY : 0);
          const box = document.createElement('div');
          box.style.cssText = `position:absolute;left:${x - 3}px;top:${y - 3}px;width:${r.width + 6}px;height:${r.height + 6}px;border:2px solid #f59e0b;border-radius:6px;box-shadow:0 0 0 2px #0006`;
          const badge = document.createElement('div');
          badge.textContent = label;
          const [bx, by] = side === 'left' ? [x - 30, y + r.height / 2 - 11] : [x - 13, y - 13];
          badge.style.cssText = `position:absolute;left:${bx}px;top:${by}px;min-width:22px;height:22px;padding:0 5px;border-radius:11px;background:#f59e0b;color:#111;font:700 13px/22px system-ui,sans-serif;text-align:center;box-shadow:0 1px 4px #0008`;
          layer.append(box, badge);
        }
      }, e.annotate);
    }

    const target = path.join(outDir, e.id + '.png');
    if (e.clip) {
      const box = await page.evaluate(sel => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height };
      }, e.clip);
      if (!box || box.width < 2 || box.height < 2) throw new Error('Clip target missing or empty: ' + e.clip);
      const pad = e.pad ?? 12;
      await page.screenshot({
        path: target,
        fullPage: true,
        clip: { x: Math.max(0, box.x - pad), y: Math.max(0, box.y - pad), width: box.width + 2 * pad, height: box.height + 2 * pad },
      });
    } else {
      await page.screenshot({ path: target, fullPage: !!e.fullPage });
    }
    report.push({ id: e.id, ok: true, errors });
    console.log('OK  ', e.id);
  } catch (err) {
    report.push({ id: e.id, ok: false, error: String(err.message || err), errors });
    console.log('FAIL', e.id, String(err.message || err).slice(0, 200));
  }

  if (e.teardown) {
    await page.evaluate(`(async()=>{${e.teardown}\n})()`)
      .then(() => page.waitForTimeout(e.settle ?? 600))
      .catch(err => console.log('teardown failed', e.id, err.message));
  }
  await ctx.close();
  activeShot = null;
}

await browser.close();
preview.close();
console.log(JSON.stringify({
  captured: report.filter(r => r.ok && !r.skipped).length,
  skipped: report.filter(r => r.skipped).map(r => r.id),
  failed: report.filter(r => !r.ok).map(r => r.id),
  blocked_writes: preview.blocked.length,
  forwarded_writes: preview.forwarded,
}));
if (report.some(r => !r.ok)) process.exitCode = 1;
