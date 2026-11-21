# Agent 主动交付通知

每次完成一项可审阅交付（`completed` / `review` / `partial`）后，由当前执行任务的 Agent 主动调用 `notify_delivery.py` 发送一次群消息通知，不依赖后台定时轮询。

## 前置检查

发送前必须完成：
1. 在该任务的唯一主文档写入真实提交号、变更摘要、验证结果、未运行项与局限；
2. 若状态为 `completed`，先以真实 GUID 完成原生任务；若为 `review` / `partial`，原生任务保持未完成；
3. 原生任务短描述中包含与 `task_document_url` 一致的唯一任务文档链接；
4. 运行一次 `sync_tasks.py` 同步结构化状态。

## 调用方式

将本次交付写成 JSON（保留文件以便原样重试，或通过 `--delivery -` 从 stdin 传入）：

```json
{
  "task_guid": "真实任务UUID",
  "task_document_url": "https://your-tenant.feishu.cn/wiki/TaskDocNode",
  "delivery_id": "v0.4.0-rc1-review",
  "status": "review",
  "summary": "本次实际改动与结果摘要",
  "revision": "main abc1234..def5678",
  "validation": "pytest 42 passed; docs check passed",
  "limitations": "UI 体验待人工验收（无则写无）",
  "documents": [
    { "title": "在线文档章节", "url": "https://example.org/docs/guide/feature" }
  ]
}
```

预览与发送：

```bash
python3 <skills_dir>/soar-devflow-tasks/scripts/notify_delivery.py --delivery delivery.json --dry-run
python3 <skills_dir>/soar-devflow-tasks/scripts/notify_delivery.py --delivery delivery.json
```

## 幂等、去重与失败处理

- 脚本只读取目标任务及必要祖先以校验归属，不扫描全清单、不修改任务状态。
- 本地状态文件（`notifications.json` 中的 `state_path`）使用文件锁、原子写入（`0600` + `fsync`）并在发信前落盘幂等 UUID。
- 相同 `(task_guid, delivery_id)` 且内容一致的重复调用直接返回 `already_sent`；**相同 `delivery_id` 改了内容会被拒绝**，修订重发必须换新 `delivery_id`。
- 发送失败时返回非零退出码与 `retry_after_seconds`，Agent 最多按提示等待后原样重试一次；仍失败直接如实报告，不安排后台静默重试。
- 若发信结果不明超过 50 分钟，状态转为 `needs_reconciliation`，须先人工核对群消息，绝不删除状态文件或换 ID 绕过去重。
