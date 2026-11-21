// In-place zoom modal for figures, SVG diagrams, and Mermaid charts.
const TEXT = {
  zh: { dialog: '图片预览', zoomIn: '放大', zoomOut: '缩小', fit: '适应窗口', original: '新标签页打开原图', close: '关闭（Esc）', hint: '拖动或滚轮平移 · Ctrl+滚轮或双击缩放 · Esc 关闭' },
  en: { dialog: 'Image preview', zoomIn: 'Zoom in', zoomOut: 'Zoom out', fit: 'Fit', original: 'Open original', close: 'Close (Esc)', hint: 'Drag/scroll to pan · Ctrl+wheel or double-click to zoom · Esc to close' },
};
const text = () => TEXT[(document.documentElement.lang || '').toLowerCase().startsWith('en') ? 'en' : 'zh'];
let dialog, stage, content, zoomLabel, originalLink, caption;
let s = 1, x = 0, y = 0, fit = 1, size = [1, 1], vector = false;

function build() {
  dialog = document.createElement('dialog');
  dialog.className = 'sd-lightbox';
  dialog.innerHTML = `<div class="sd-lightbox-stage"><div class="sd-lightbox-content"></div></div>
<div class="sd-lightbox-bar"><button type="button" data-act="out">−</button><button type="button" data-act="fit" class="sd-lightbox-zoom">100%</button><button type="button" data-act="in">+</button><a class="sd-lightbox-original" target="_blank" rel="noopener">↗</a><button type="button" data-act="close">×</button></div>
<div class="sd-lightbox-foot"><p class="sd-lightbox-caption"></p><p class="sd-lightbox-hint"></p></div>`;
  document.body.append(dialog);
  stage = dialog.querySelector('.sd-lightbox-stage');
  content = dialog.querySelector('.sd-lightbox-content');
  zoomLabel = dialog.querySelector('.sd-lightbox-zoom');
  originalLink = dialog.querySelector('.sd-lightbox-original');
  caption = dialog.querySelector('.sd-lightbox-caption');
  dialog.querySelector('.sd-lightbox-bar').addEventListener('click', ev => {
    const act = ev.target.closest('button')?.dataset.act;
    if (act === 'close') dialog.close();
    else if (act === 'fit') fitView();
    else if (act === 'in' || act === 'out') zoom(act === 'in' ? 1.4 : 1 / 1.4);
  });
  stage.addEventListener('click', ev => { if (!content.contains(ev.target)) dialog.close(); });
  stage.addEventListener('dblclick', () => { s = s > fit * 1.05 ? fit : fit * 2; center(); apply(); });
  stage.addEventListener('wheel', ev => { ev.preventDefault(); zoom(Math.exp(-ev.deltaY * 0.002)); }, { passive: false });
}
function center() { const r = stage.getBoundingClientRect(); x = (r.width - size[0] * s) / 2; y = Math.max(56, (r.height - size[1] * s) / 2); }
function apply() { content.style.transform = `translate(${x}px,${y}px) scale(${s})`; zoomLabel.textContent = Math.round(s * 100) + '%'; }
function zoom(f) { s = Math.min(6, Math.max(0.2, s * f)); center(); apply(); }
function fitView() {
  const r = stage.getBoundingClientRect();
  const cap = vector ? Infinity : 1;
  fit = Math.min(cap, (r.width - 48) / size[0], (r.height - 130) / size[1]);
  s = Math.max(0.1, fit); center(); apply();
}
function openItem(item) {
  if (!dialog) build();
  const t = text();
  content.replaceChildren();
  vector = item.kind !== 'raster';
  if (item.kind === 'mermaid') {
    const clone = item.svg.cloneNode(true);
    const r = item.svg.getBoundingClientRect();
    clone.setAttribute('width', r.width); clone.setAttribute('height', r.height);
    const wrap = document.createElement('div'); wrap.className = 'vp-doc mermaid'; wrap.append(clone);
    content.append(wrap);
    size = [Math.max(1, r.width), Math.max(1, r.height)];
    dialog.showModal(); fitView();
  } else {
    const img = new Image(); img.src = item.src; img.alt = item.alt || '';
    content.append(img);
    dialog.showModal();
    const ready = () => { size = [Math.max(1, img.naturalWidth || 900), Math.max(1, img.naturalHeight || 500)]; fitView(); };
    if (img.complete && img.naturalWidth) ready(); else img.onload = ready;
  }
  caption.textContent = item.caption || '';
  dialog.querySelector('.sd-lightbox-hint').textContent = t.hint;
  originalLink.hidden = item.kind === 'mermaid';
  if (item.src) originalLink.href = item.src;
}
export function installLightbox() {
  if (typeof window === 'undefined' || window.__sdLightbox) return;
  window.__sdLightbox = true;
  document.addEventListener('click', ev => {
    if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey) return;
    const doc = ev.target.closest?.('.vp-doc');
    if (!doc || ev.target.closest('.sd-lightbox')) return;
    const chart = ev.target.closest('.mermaid');
    if (chart) {
      const svg = chart.querySelector(':scope > svg');
      if (svg) { ev.preventDefault(); openItem({ kind: 'mermaid', svg }); }
      return;
    }
    const fig = ev.target.closest('figure.sd-figure');
    const img = fig ? fig.querySelector('img') : ev.target.closest('img');
    if (!img || img.closest('.VPHero')) return;
    ev.preventDefault();
    const src = img.currentSrc || img.src;
    openItem({ kind: /\.svg($|[?#])/i.test(src) ? 'svg' : 'raster', src, alt: img.alt, caption: fig?.querySelector('figcaption')?.textContent || img.alt });
  });
}
