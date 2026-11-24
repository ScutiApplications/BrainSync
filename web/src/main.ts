import { createApp } from "vue";
import "./style.css";
import { initTheme } from "./composables/useTheme";
import App from "./App.vue";
import { router } from "./router";

initTheme();

createApp(App).use(router).mount("#app");
