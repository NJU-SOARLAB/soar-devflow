---
layout: home

hero:
  name: SOAR DevFlow
  text: Process Management & Docs Workflow for Large Projects
  tagline: Born from vibe coding complex robotics systems—track real task progress and dual-timeline schedules in Feishu/Lark while maintaining clean VitePress tutorials and design docs in Git.
  image:
    src: /logo.png
    alt: SOAR DevFlow Logo
  actions:
    - theme: brand
      text: Setup with Your Agent
      link: /en/guide/quickstart
    - theme: alt
      text: Live Kanban & Gantt Demo
      link: /en/guide/live-demo
    - theme: alt
      text: GitHub Repository
      link: https://github.com/NJU-SOARLAB/soar-devflow

features:
  - title: Just Send the Repo Link to Your Agent
    details: The bottom half of README gives your coding agent clear setup instructions—it checks your environment, asks a few quick questions, and configures everything interactively.
  - title: Separate AI Coding Hours from Human Review Days
    details: Agents finish coding in hours while human reviews and hardware tests take days. Switch between both timelines cleanly in the interactive Kanban and Gantt view.
  - title: '"Code Written" Is Not "Done"'
    details: Tasks close automatically only when automated checks genuinely cover and pass everything; items needing human review stay open and post a summary to group chat.
  - title: Clean Tutorials & Design Docs in Git
    details: Keep sprint logs in Feishu instead of cluttering the repo with stale TODO files. Includes writing templates, auto-annotated UI screenshots, and pre-commit doc checks.
---

<div class="sd-home-section">

<div class="sd-institutions">
  <a href="https://www.soar-lab.org/" target="_blank" rel="noopener">
    <img src="/institutions.png" alt="Nanjing University · SOARLAB@NJU" />
  </a>
</div>

## Paste This to Your Coding Agent to Set Everything Up

Copy the prompt below into **Claude Code, Codex, Antigravity, or Cursor** inside your project. Your agent will ask about your setup preferences, preview any remote boards with `--dry-run`, and verify everything end-to-end:

<AgentPromptBox lang="en" />

## How the Workflow Fits Together

<div class="sd-arch-showcase">
  <img src="/architecture-en.png" alt="SOAR DevFlow Large-Project Workflow" />
</div>

## Where to Read Next

<div class="sd-grid">
  <a class="sd-card" href="./guide/quickstart.html">
    <strong>1. Quickstart →</strong>
    <span>Walk through interactive agent onboarding or set everything up manually in four CLI steps.</span>
  </a>
  <a class="sd-card" href="./guide/task-workflow.html">
    <strong>2. Process Management →</strong>
    <span>How tasks, rolling minor-fix logs, dual-timeline Gantt charts, and group notifications work day to day.</span>
  </a>
  <a class="sd-card" href="./guide/docs-craft.html">
    <strong>3. Docs Site &amp; Tutorials →</strong>
    <span>How to write clear tutorials and design docs, auto-capture numbered UI screenshots, and catch doc bugs early.</span>
  </a>
  <a class="sd-card" href="./guide/live-demo.html">
    <strong>4. Live Kanban &amp; Gantt Demo →</strong>
    <span>Try the interactive HTML5 board and dual-timeline Gantt widget directly in your browser.</span>
  </a>
</div>

</div>
