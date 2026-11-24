<script setup lang="ts">
import { RouterLink, useRoute } from "vue-router";
import { NAV_PAGES } from "../router/pages";

/** The sidebar: one link per page. Collapsed it shows named icons. */
defineProps<{ expanded: boolean }>();
const route = useRoute();
</script>

<template>
  <aside id="brain-sidebar" class="sidebar" :class="{ expanded }" aria-label="BrainSync">
    <nav aria-label="Sections">
      <RouterLink v-for="page in NAV_PAGES" :key="page.to" :to="page.to" :title="page.label" :aria-label="page.label"
        :aria-current="route.path === page.to ? 'page' : undefined">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path v-for="d in page.icon" :key="d" :d="d" /></svg>
        <span v-if="expanded">{{ page.label }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar { display: flex; flex-direction: column; flex: none; width: 52px; padding: 8px; gap: 12px; border-inline-end: 1px solid var(--border); background: var(--bg); overflow-y: auto; scrollbar-gutter: stable; }
.sidebar.expanded { width: 210px; }
nav { display: grid; gap: 4px; }
a { position: relative; display: flex; align-items: center; justify-content: center; gap: 9px; min-height: 36px; border-radius: var(--radius-md); color: var(--muted); text-decoration: none; font-size: 0.84rem; }
.expanded a { justify-content: flex-start; padding-inline: 8px; }
a:hover, a[aria-current="page"] { background: var(--surface); color: var(--text); }
a[aria-current="page"] { box-shadow: inset 2px 0 var(--accent); }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
svg { flex: none; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
@media (max-width: 767px) {
  .sidebar.expanded { width: 100%; max-height: 45dvh; border-inline-end: 0; border-bottom: 1px solid var(--border); }
  .sidebar a { min-height: 44px; }
}
</style>
