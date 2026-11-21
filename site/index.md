---
layout: home

hero:
  name: SOAR DevFlow
  text: 大项目开发的进度管理与技术文档工作流
  tagline: 源自机器人复杂系统 Vibe 开发实战：一边用飞书把任务、排期和真实验收管明白，一边用 VitePress 写出清楚耐读的教程与设计文档。
  image:
    src: /logo.png
    alt: SOAR DevFlow Logo
  actions:
    - theme: brand
      text: 发给 Agent 自动配好
      link: /guide/quickstart
    - theme: alt
      text: 在线试玩看板与甘特图
      link: /guide/live-demo
    - theme: alt
      text: GitHub 仓库
      link: https://github.com/NJU-SOARLAB/soar-devflow

features:
  - title: 把链接甩给 Agent 就行
    details: 仓库 README 后半段写好了给 Agent 看的安装步骤。你的 Agent 会自己检查环境、问你几个问题、自动建好飞书表格和文档站。
  - title: AI 写代码时间 vs 人工验收时间分开排
    details: AI 几小时写完代码，但人审方案、上设备测试往往要几天。内置交互式看板与双时间轴甘特图，不再把两件事糊在一张表里。
  - title: 不把“刚写完代码”当“已完成”
    details: 自动测试能完全覆盖且跑通的才关单；需要人看或真机验证的保持未完成，做完自动往飞书群发一条带证据的交付提醒。
  - title: 代码库只留真正有用的教程与文档
    details: 过程记录留在飞书，不在代码库堆满过期的 TODO.md。内置教程/说明模板、自动网页截图标号工具，以及防断链缺图的检查脚本。
---

<div class="sd-home-section">

<div class="sd-institutions">
  <a href="https://www.soar-lab.org/" target="_blank" rel="noopener">
    <img src="/institutions.png" alt="Nanjing University · SOARLAB@NJU" />
  </a>
</div>

## 一句话发给你的 Coding Agent，对话式配好整套流程

把下面这段话直接发给 **Claude Code / Codex / Antigravity / Cursor**，它会先问清楚你的项目偏好、给你预览要建的表格，确认后再动手：

<AgentPromptBox lang="zh" />

## 整套工作流是怎么转起来的？

<div class="sd-arch-showcase">
  <img src="/architecture-zh.png" alt="SOAR DevFlow 大项目开发管理与文档工作流" />
</div>

## 接下来看哪篇？

<div class="sd-grid">
  <a class="sd-card" href="./guide/quickstart.html">
    <strong>1. 快速上手 →</strong>
    <span>看 Agent 自动配置完整过程，或者自己用命令行分四步装好。</span>
  </a>
  <a class="sd-card" href="./guide/task-workflow.html">
    <strong>2. 飞书过程管理 →</strong>
    <span>怎么管大项目任务、记小修日志、排双时间轴甘特图、做真实验收与群通知。</span>
  </a>
  <a class="sd-card" href="./guide/docs-craft.html">
    <strong>3. 文档站与教程编写 →</strong>
    <span>怎么写让人照着就能跑通的教程、自动给网页截图打标号、用脚本拦住断链缺图。</span>
  </a>
  <a class="sd-card" href="./guide/live-demo.html">
    <strong>4. 看板与甘特图在线演示 →</strong>
    <span>直接在网页里点点看同步脚本生成的交互式看板与双时间轴甘特图。</span>
  </a>
</div>

</div>
