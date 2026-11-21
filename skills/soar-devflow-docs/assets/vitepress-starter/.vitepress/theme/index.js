import DefaultTheme from 'vitepress/theme';
import { onMounted } from 'vue';
import { installLightbox } from './lightbox.js';
import './custom.css';

export default {
  ...DefaultTheme,
  setup() {
    onMounted(() => {
      installLightbox();
    });
  },
};
