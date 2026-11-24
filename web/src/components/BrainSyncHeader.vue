<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { logout } from "../session";
import ThemeSelect from "./ThemeSelect.vue";

/** The compact full-width header: sidebar toggle, identity, page title, and Help and Profile. */
defineProps<{ title: string; expanded: boolean }>();
defineEmits<{ toggle: [] }>();
const route = useRoute();
const panel = ref<"help" | "profile">();
const trigger = ref<HTMLElement>();
const header = ref<HTMLElement>();

function toggle(next: "help" | "profile", event: MouseEvent) {
  panel.value = panel.value === next ? undefined : next;
  if (panel.value) trigger.value = event.currentTarget as HTMLElement;
}

function dismiss() {
  if (!panel.value) return;
  panel.value = undefined;
  trigger.value?.focus();
}

function closeOutside(event: PointerEvent) {
  if (event.target instanceof Node && !header.value?.contains(event.target)) panel.value = undefined;
}

onMounted(() => document.addEventListener("pointerdown", closeOutside));
onUnmounted(() => document.removeEventListener("pointerdown", closeOutside));
watch(() => route.fullPath, () => { panel.value = undefined; });
</script>

<template>
  <header ref="header" class="brain-header" @keydown.esc.stop="dismiss">
    <button type="button" class="admin-icon" aria-controls="brain-sidebar" :aria-expanded="expanded"
      :title="expanded ? 'Collapse sidebar' : 'Expand sidebar'" :aria-label="expanded ? 'Collapse sidebar' : 'Expand sidebar'" @click="$emit('toggle')">
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M9 5v14" /></svg>
    </button>
    <span class="brand">BrainSync</span>
    <h1 v-if="title">{{ title }}</h1>
    <div class="header-controls">
      <button type="button" class="admin-icon" title="Help" aria-label="Help" :aria-expanded="panel === 'help'" @click="toggle('help', $event)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9 9a3 3 0 1 1 5 2c-1.5 1-2 1.5-2 3m0 3h.01" /></svg>
      </button>
      <button type="button" class="admin-icon profile" title="Profile" aria-label="Profile" :aria-expanded="panel === 'profile'" @click="toggle('profile', $event)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>
      </button>
    </div>
    <section v-if="panel" class="header-popover" :aria-label="panel">
      <template v-if="panel === 'help'">
        <strong>Help</strong>
        <p>Vaults lists your Brain vaults. Export packs chosen notes into a file. Import brings a pack or a sharing device's notes in, with a merge view for conflicts. Share lets another device on this network pull what you choose. Agent setup installs the Claude Code and Codex config. Every setting is saved in the database and applies at once.</p>
      </template>
      <template v-else>
        <strong>Profile</strong>
        <ThemeSelect />
        <button type="button" class="logout" @click="logout()">Log out</button>
      </template>
    </section>
  </header>
</template>

<style scoped>
.brain-header { position: relative; z-index: 2; display: flex; align-items: center; gap: 10px; min-height: 46px; padding: 4px 10px; border-bottom: 1px solid var(--border); background: var(--bg); }
.brand { flex: none; color: var(--accent); font-weight: 700; font-size: 0.88rem; }
h1 { min-width: 0; padding-inline-start: 10px; border-inline-start: 1px solid var(--border); margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.88rem; font-weight: 600; }
.header-controls { display: flex; gap: 4px; margin-inline-start: auto; }
.profile { background: var(--surface); color: var(--text); }
.header-popover { position: absolute; inset: calc(100% + 4px) 8px auto auto; display: grid; gap: 10px; width: min(265px, calc(100vw - 16px)); max-height: 70dvh; overflow: auto; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg); overflow-wrap: anywhere; }
.header-popover p { margin: 0; color: var(--muted); font-size: 0.86rem; }
.logout { padding: 6px 12px; border: 1px solid var(--border); border-radius: var(--radius-full); background: transparent; color: var(--text); cursor: pointer; font: inherit; }
.logout:hover { background: var(--surface); }
@media (max-width: 767px) {
  .brain-header { padding-inline: 4px; gap: 4px; }
  h1 { padding-inline-start: 4px; }
  .header-controls { gap: 0; }
}
</style>
