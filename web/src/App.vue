<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import BrainNav from "./components/BrainNav.vue";
import BrainSyncHeader from "./components/BrainSyncHeader.vue";
import ThemeSelect from "./components/ThemeSelect.vue";
import { pageTitle } from "./router/pages";
import { session } from "./session";

const route = useRoute();
const router = useRouter();
const signedInShell = computed(() => session.authed && !route.meta.guestOnly);
const title = computed(() => pageTitle(route.path));
const viewport = window.matchMedia("(max-width: 767px)");
const narrow = ref(viewport.matches);
const desktopExpanded = ref(true);
const mobileExpanded = ref(false);
const expanded = computed(() => (narrow.value ? mobileExpanded.value : desktopExpanded.value));

function syncViewport(event: MediaQueryListEvent) {
  narrow.value = event.matches;
  mobileExpanded.value = false;
}

function toggleNav() {
  if (narrow.value) mobileExpanded.value = !mobileExpanded.value;
  else desktopExpanded.value = !desktopExpanded.value;
}

onMounted(() => viewport.addEventListener("change", syncViewport));
onUnmounted(() => viewport.removeEventListener("change", syncViewport));
watch(() => route.fullPath, () => { mobileExpanded.value = false; });
// The login can end mid-page (expired, password changed elsewhere): go back to Login.
watch(() => session.authed, (now) => {
  if (!now && !route.meta.guestOnly) void router.replace({ name: "login" });
});
</script>

<template>
  <div class="shell" :class="{ 'brain-shell': signedInShell }">
    <BrainSyncHeader v-if="signedInShell" :title="title" :expanded="expanded" @toggle="toggleNav" />
    <ThemeSelect v-else class="guest-theme" />
    <div class="shell-body">
      <BrainNav v-if="signedInShell" v-show="!narrow || expanded" :expanded="expanded" />
      <main class="shell-page"><RouterView /></main>
    </div>
  </div>
</template>

<style scoped>
.shell { position: relative; }
.shell, .shell-page { display: flex; flex: 1; flex-direction: column; min-height: 0; min-width: 0; }
.shell-body { display: flex; flex: 1; min-height: 0; min-width: 0; }
.brain-shell .shell-page { background: var(--surface); }
.brain-shell :deep(.page-head-copy) { display: none; }
.brain-shell :deep(.page-head:not(:has(.page-actions))) { display: none; }
.guest-theme { position: absolute; inset: 8px 12px auto auto; z-index: 2; }
@media (max-width: 767px) { .shell-body { flex-direction: column; } }
</style>
