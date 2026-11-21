# 声明式可复现截图与编号标注清单

手工截图在 UI 演进两轮后就会全部过时。SOAR DevFlow 用 JSON 配置驱动 Playwright 自动打开页面、框选元素并画上 ①②③ 编号标注；截图期间自动拦截写请求，避免误操作正在运行的服务。

## 清单格式（`shots/<page>.json`）

```json
[
  {
    "id": "quickstart-hero",
    "page": "/",
    "theme": "dark",
    "viewport": [1440, 900],
    "wait": 1500,
    "setup": "document.querySelector('#advanced')?.setAttribute('open', '')",
    "clip": "#main-panel",
    "pad": 12,
    "annotate": [
      { "selector": "#primary-action", "label": "1" },
      { "selector": "#status-badge", "label": "2", "badge": "left" }
    ],
    "storage": { "theme": "dark" },
    "caption": {
      "zh": "主控制台入口与状态栏速览",
      "en": "Main console entry and status bar"
    }
  }
]
```

## 运行命令

```bash
# 列出全部已声明截图
node <skills_dir>/soar-devflow-docs/scripts/capture_shots.mjs --list

# 仅重拍指定截图（本地只读代理会拦住全部 POST/PUT/DELETE 写请求）
node <skills_dir>/soar-devflow-docs/scripts/capture_shots.mjs --upstream http://127.0.0.1:5173 --only quickstart-hero
```

## 扩展 Hook（面向 WebGL / 视频流 / Canvas 等特殊前端）

通过 `--hook ./my-shot-hook.mjs` 可注入项目专属行为（无需改动开源核心脚本），支持可选导出：
- `beforePage(ctx, shot, options)`：页面创建前注入 init script 或解码 shim
- `afterGoto(page, shot, options)`：等待自定义流帧、WebGL 或 Canvas 渲染就绪
- `beforeAnnotate(page, shot, options)`：动态注入虚拟标注框（如 Canvas HUD 区域）
- `allowWrite(pathname, jsonBody, shot)`：仅在显式开启 `--allow-writes` 时放行极少数只读视觉命令（如切换相机视角）
