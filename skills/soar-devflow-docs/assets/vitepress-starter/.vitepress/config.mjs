import { defineConfig } from 'vitepress';
import { withMermaid } from 'vitepress-plugin-mermaid';
import fs from 'node:fs';

const BASE = '@@BASE@@';
const BILINGUAL = @@BILINGUAL@@;
const coverage = JSON.parse(fs.readFileSync(new URL('../coverage.json', import.meta.url), 'utf8'));

const figures = base => md => {
  md.core.ruler.push('sd_figures', state => {
    const tokens = state.tokens;
    for (let i = 0; i + 2 < tokens.length; i++) {
      if (tokens[i].type !== 'paragraph_open' || tokens[i + 1].type !== 'inline' || tokens[i + 2].type !== 'paragraph_close') continue;
      const children = tokens[i + 1].children.filter(c => !(c.type === 'text' && !c.content.trim()) && c.type !== 'softbreak');
      if (children.length !== 1 || children[0].type !== 'image') continue;
      const image = children[0];
      const alt = image.children.map(c => c.content).join('');
      tokens[i].tag = tokens[i + 2].tag = 'figure';
      tokens[i].attrSet('class', 'sd-figure');
      const src = image.attrGet('src') || '';
      const open = new state.Token('html_inline', '', 0);
      open.content = `<a href="${md.utils.escapeHtml(src.startsWith('/') ? base + src.slice(1) : src)}" target="_blank" rel="noopener" aria-haspopup="dialog">`;
      const close = new state.Token('html_inline', '', 0);
      close.content = '</a>' + (alt ? `<figcaption>${md.utils.escapeHtml(alt)}</figcaption>` : '');
      tokens[i + 1].children = [open, image, close];
    }
  });
};

const sections = {
  guide: { zh: '教程 · 怎么用', en: 'Tutorials · how to use' },
  reference: { zh: '说明 · 设计与原理', en: 'Reference · design & internals' },
  spec: { zh: '规范 · 接口与契约', en: 'Specifications' },
};

const sidebarFor = (lang, prefix) =>
  Object.entries(sections)
    .map(([section, label]) => {
      const items = Object.entries(coverage)
        .filter(([, info]) => info.section === section)
        .map(([key, info]) => ({ text: info[`title_${lang}`] || key, link: `${prefix}/${key}` }));
      return items.length ? { text: label[lang], collapsed: false, items } : null;
    })
    .filter(Boolean);

const locales = BILINGUAL
  ? {
      root: {
        label: '简体中文',
        lang: 'zh-CN',
        themeConfig: {
          outline: { label: '本页内容', level: [2, 3] },
          sidebar: sidebarFor('zh', ''),
          nav: [{ text: '教程', link: '/guide/quickstart' }, { text: '说明', link: '/reference/architecture' }],
          docFooter: { prev: '上一页', next: '下一页' },
          darkModeSwitchLabel: '外观',
          returnToTopLabel: '回到顶部',
          sidebarMenuLabel: '目录',
        },
      },
      en: {
        label: 'English',
        lang: 'en-US',
        themeConfig: {
          outline: { level: [2, 3] },
          sidebar: sidebarFor('en', '/en'),
          nav: [{ text: 'Tutorials', link: '/en/guide/quickstart' }, { text: 'Reference', link: '/en/reference/architecture' }],
        },
      },
    }
  : undefined;

export default withMermaid(defineConfig({
  title: '@@TITLE@@',
  description: '@@DESCRIPTION@@',
  base: BASE,
  lang: 'zh-CN',
  lastUpdated: false,
  cleanUrls: false,
  locales,
  themeConfig: {
    outline: { label: '本页内容', level: [2, 3] },
    sidebar: BILINGUAL ? undefined : sidebarFor('zh', ''),
    nav: BILINGUAL ? undefined : [{ text: '教程', link: '/guide/quickstart' }, { text: '说明', link: '/reference/architecture' }],
    search: {
      provider: 'local',
      options: {
        miniSearch: {
          options: {
            tokenize: text =>
              Array.from(new Intl.Segmenter('zh', { granularity: 'word' }).segment(text))
                .filter(x => x.isWordLike)
                .map(x => x.segment),
          },
        },
      },
    },
    footer: { message: 'Built with SOAR DevFlow' },
  },
  markdown: {
    math: true,
    theme: { light: 'github-light', dark: 'github-dark' },
    image: { lazyLoading: true },
    config: md => md.use(figures(BASE)),
  },
  mermaid: { securityLevel: 'strict' },
  mermaidPlugin: { class: 'mermaid sd-mermaid' },
}));
