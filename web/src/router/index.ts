import { createRouter, createWebHashHistory } from "vue-router";
import { refreshSession, session } from "../session";

// Hash history: the page works at / and under a proxy prefix (/s/<id>/) with no server-side fallback.
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/vaults" },
    { path: "/login", name: "login", component: () => import("../views/LoginView.vue"), meta: { guestOnly: true } },
    { path: "/vaults", component: () => import("../views/VaultsView.vue") },
    { path: "/export", component: () => import("../views/ExportView.vue") },
    { path: "/import", component: () => import("../views/ImportView.vue") },
    { path: "/share", component: () => import("../views/ShareView.vue") },
    { path: "/sync", component: () => import("../views/SyncView.vue") },
    { path: "/setup", component: () => import("../views/SetupView.vue") },
    { path: "/history", component: () => import("../views/HistoryView.vue") },
    { path: "/settings", component: () => import("../views/SettingsView.vue") },
    { path: "/:rest(.*)", redirect: "/vaults" },
  ],
});

router.beforeEach(async (to) => {
  if (!session.checked) await refreshSession().catch(() => {});
  if (!session.authed && !to.meta.guestOnly) return { name: "login" };
  if (session.authed && to.meta.guestOnly) return { path: "/vaults" };
  return true;
});
