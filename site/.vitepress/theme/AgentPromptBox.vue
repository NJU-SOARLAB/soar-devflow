<script setup>
import { ref, computed } from 'vue';

const props = defineProps({
  lang: { type: String, default: 'zh' },
});

const tab = ref('agent');
const copied = ref(false);

const agentPrompt = computed(() =>
  props.lang === 'en'
    ? `Please read https://github.com/NJU-SOARLAB/soar-devflow/blob/main/README.en.md\n(including the Setup Instructions for Coding Agents at the bottom), ask me about my\nproject preferences, and install, configure, and verify SOAR DevFlow in this repository.`
    : `请阅读 https://github.com/NJU-SOARLAB/soar-devflow 的 README（包含底部的 Agent 配置说明），\n先问清楚我的项目设置偏好，然后在当前仓库帮我装好并验证 SOAR DevFlow。`
);

const cliSnippet = computed(() =>
  `git clone https://github.com/NJU-SOARLAB/soar-devflow.git ~/.cache/soar-devflow\npython3 ~/.cache/soar-devflow/skills/soar-devflow-setup/scripts/install_skills.py \\\n  --target . --scope workspace --mode copy`
);

const activeText = computed(() => (tab.value === 'agent' ? agentPrompt.value : cliSnippet.value));

async function copyText() {
  try {
    await navigator.clipboard.writeText(activeText.value);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 1800);
  } catch {
    copied.value = false;
  }
}
</script>

<template>
  <div class="sd-prompt-box">
    <div class="sd-prompt-head">
      <div class="sd-prompt-tabs" role="tablist">
        <button type="button" :class="{ active: tab === 'agent' }" @click="tab = 'agent'">
          {{ lang === 'en' ? 'Send to Coding Agent (Recommended)' : '发给你的 Coding Agent（推荐）' }}
        </button>
        <button type="button" :class="{ active: tab === 'cli' }" @click="tab = 'cli'">
          {{ lang === 'en' ? 'Manual CLI Install' : '命令行手动安装' }}
        </button>
      </div>
      <button type="button" class="sd-copy-btn" @click="copyText">
        {{ copied ? (lang === 'en' ? 'Copied ✓' : '已复制 ✓') : (lang === 'en' ? 'Copy' : '复制') }}
      </button>
    </div>
    <pre class="sd-prompt-code"><code>{{ activeText }}</code></pre>
    <p class="sd-prompt-foot">
      {{
        lang === 'en'
          ? 'Works with Claude Code, Codex, Antigravity, Cursor, and other Agent Skills-compatible tools.'
          : '支持 Claude Code、Codex、Antigravity、Cursor 等支持 Agent Skills 的编程工具。'
      }}
    </p>
  </div>
</template>
