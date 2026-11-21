---
translationKey: guide/live-demo
sourceRevision: 2
---

# 看板与甘特图在线演示

下面这个可交互面板不是切图，而是直接用本仓库的 `render_overview.py` 渲染出来的真实单文件网页。平时跑完 `sync_tasks.py`，这个面板就会自动更新到你们飞书任务汇总页的顶部，不用额外部署任何后台服务。

## 直接点点看 {#playground}

<iframe class="sd-demo-frame" src="/soar-devflow/demo/overview-demo.html" title="SOAR DevFlow 交互式项目推进总览演示"></iframe>

## 可以试这几个地方 {#how-to-explore}

1. **筛选与搜索**：顶部默认只看 `未完成任务`（省得做完的旧任务把屏幕占满），你可以切到 `全部任务` 或 `已完成任务`，也可以按阶段、领域、主/子任务筛选，或者直接搜编号。
2. **三种看板视角**：在「TODO 看板」里点选 `按项目阶段`、`按优先级`、`按执行状态`；把鼠标悬停在卡片上，能直接看到这项任务的 AI 预估工时、人工验收时间、等待原因和前置任务。
3. **两条甘特时间线切换**：切到「甘特时间轴」标签，点一下左上角的切换按钮对比：
   - **AI 实施窗口**：看 Agent 侧几小时一段的开发排期（子任务用细条显示）；
   - **交付 / 验收窗口**：拉回到按天看的整体排期，一眼看出哪项工作卡在人工评审或等设备上。

## 怎么离线生成这个页面？ {#how-generated}

除了同步到飞书文档里，你随时可以用一条命令把任意任务 JSON 渲染成独立网页（本页的演示就是这么生成的）：

```bash
python3 skills/soar-devflow-tasks/scripts/render_overview.py \
  --data site/demo-fixture.json \
  --output site/public/demo/overview-demo.html
```

生成的 HTML 自带数据转义与链接域名白名单检查，嵌在文档 iframe 里既轻量又安全。

## 相关说明

- 查看阶段顺序、颜色与时区配置方法：[配置文件说明](../reference/config-schema.md#tasks-json)
- 查看同步与渲染脚本命令行参数：[脚本与命令行说明](../reference/cli-scripts.md#task-scripts)
