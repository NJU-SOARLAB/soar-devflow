import DefaultTheme from 'vitepress/theme';
import { onMounted } from 'vue';
import AgentPromptBox from './AgentPromptBox.vue';
import { installLightbox } from './lightbox.js';
import './custom.css';

export default {
  ...DefaultTheme,
  enhanceApp(ctx) {
    DefaultTheme.enhanceApp?.(ctx);
    ctx.app.component('AgentPromptBox', AgentPromptBox);
  },
  setup() {
    onMounted(() => {
      installLightbox();
    });
  },
};
