import { defineConfig } from 'vitepress';
import { withMermaid } from 'vitepress-plugin-mermaid';
import fs from 'node:fs';

const BASE = '/soar-devflow/';
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
  guide: { zh: '使用指南', en: 'Guides' },
  reference: { zh: '配置与脚本参考', en: 'Reference' },
};

const sidebarFor = (lang, prefix) =>
  Object.entries(sections).map(([section, label]) => ({
    text: label[lang],
    collapsed: false,
    items: Object.entries(coverage)
      .filter(([, info]) => info.section === section)
      .map(([key, info]) => ({ text: info[`title_${lang}`], link: `${prefix}/${key}` })),
  }));

export default withMermaid(defineConfig({
  title: 'SOAR DevFlow',
  description: 'Process Management & Technical Documentation Workflow for Large Projects',
  base: BASE,
  lang: 'zh-CN',
  lastUpdated: false,
  cleanUrls: false,
  head: [
    ['link', { rel: 'icon', type: 'image/png', href: `${BASE}favicon.png` }],
  ],
  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
      themeConfig: {
        outline: { label: '本页目录', level: [2, 3] },
        sidebar: sidebarFor('zh', ''),
        nav: [
          { text: '快速上手', link: '/guide/quickstart' },
          { text: '过程管理', link: '/guide/task-workflow' },
          { text: '文档与教程', link: '/guide/docs-craft' },
          { text: '看板演示', link: '/guide/live-demo' },
          { text: '参考说明', link: '/reference/architecture' },
        ],
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
        nav: [
          { text: 'Quickstart', link: '/en/guide/quickstart' },
          { text: 'Process Tracking', link: '/en/guide/task-workflow' },
          { text: 'Docs & Tutorials', link: '/en/guide/docs-craft' },
          { text: 'Live Demo', link: '/en/guide/live-demo' },
          { text: 'Reference', link: '/en/reference/architecture' },
        ],
      },
    },
  },
  themeConfig: {
    logo: '/logo.png',
    siteTitle: 'SOAR DevFlow',
    socialLinks: [
      { icon: 'github', link: 'https://github.com/NJU-SOARLAB/soar-devflow' },
    ],
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
    footer: {
      message: 'MIT License · SOARLAB, Nanjing University',
      copyright: 'Copyright © 2026 SOARLAB · soar-lab.org/soar-devflow',
    },
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
