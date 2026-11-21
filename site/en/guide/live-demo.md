---
translationKey: guide/live-demo
sourceRevision: 2
---

# Live Kanban & Gantt Demo

The interactive board below is a standalone single-file HTML widget rendered directly by `render_overview.py` in this repository. In real projects, `sync_tasks.py` embeds this widget at the top of your Feishu/Lark task overview page—no separate web server needed.

## Try It Live {#playground}

<iframe class="sd-demo-frame" src="/soar-devflow/demo/overview-demo.html" title="SOAR DevFlow Interactive Project Overview Demo"></iframe>

## Things to Click Around {#how-to-explore}

1. **Filters & search**: Defaults to open tasks (`未完成任务`) so finished items do not crowd the view. Switch to all or completed tasks, filter by stage, domain, or main/subtask level, or search by task ID.
2. **Three Kanban groupings**: Under the **TODO 看板** tab, switch between grouping by **Stage**, **Priority**, and **Status**. Hover any card to see estimated AI hours, human review hours, wait notes, and prerequisites.
3. **Dual-timeline Gantt**: Switch to the **甘特时间轴** tab and toggle the top-left switch:
   - **AI Coding Window** (`AI 实施窗口`): Hour-scale agent implementation blocks (subtasks shown as slimmer bars);
   - **Delivery / Review Window** (`交付 / 验收窗口`): Day-scale schedule showing human review windows and hardware waits.

## How This Page Is Generated {#how-generated}

You can also render any JSON task snapshot into a standalone HTML file from the command line (which is how this demo page was built):

```bash
python3 skills/soar-devflow-tasks/scripts/render_overview.py \
  --data site/demo-fixture.json \
  --output site/public/demo/overview-demo.html
```

All embedded data is HTML/script-escaped and checked against an HTTPS domain allowlist so it runs safely inside document iframes.

## Related References

- Stage order, palette, and timezone settings: [Configuration Reference](../reference/config-schema.md#tasks-json)
- Sync and renderer CLI options: [CLI Scripts Reference](../reference/cli-scripts.md#task-scripts)
