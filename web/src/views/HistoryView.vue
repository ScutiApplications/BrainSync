<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { historyApi, type AuditEntry } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import AdminSearch from "../components/admin/AdminSearch.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** What happened (imports, exports, pulls, setting changes) and the backups made before files were replaced. */
const audit = ref<AuditEntry[]>([]);
const backups = ref<string[]>([]);
const loading = ref(true);
const error = ref("");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();

const detail = (a: AuditEntry) => JSON.stringify(Object.fromEntries(Object.entries(a).filter(([k]) => k !== "ts" && k !== "event")));
const visible = computed(() => {
  const q = search.value.trim().toLowerCase();
  return audit.value.filter((a) => !q || a.event.toLowerCase().includes(q) || detail(a).toLowerCase().includes(q));
});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const h = await historyApi.get();
    audit.value = h.audit;
    backups.value = h.backups;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>

<template>
  <PageLayout class="admin-panel" title="History" wide>
    <section class="admin-panel-card" aria-labelledby="history-log">
      <header class="admin-panel-head">
        <h2 id="history-log">Activity</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Activity"><p>Newest first. Each import, export, device pull, setup run and setting change is recorded in the database.</p></PanelHelp>
          <AdminSearch ref="searchField" v-model="search" label="Search activity" />
        </div>
      </header>
      <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text"><button type="button" class="chip" @click="load">Retry</button></ActionMessage>
      <p v-else-if="loading" class="admin-panel-text muted" role="status">Loading activity…</p>
      <p v-else-if="!audit.length" class="admin-panel-text muted">Nothing has happened yet.</p>
      <p v-else-if="!visible.length" class="admin-panel-text muted">No activity matches your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="history-log">
        <table class="admin-records">
          <thead><tr><th scope="col">When</th><th scope="col">What</th><th scope="col">Details</th></tr></thead>
          <tbody>
            <tr v-for="(a, i) in visible" :key="i"><td>{{ a.ts }}</td><th scope="row">{{ a.event }}</th><td class="mono">{{ detail(a) }}</td></tr>
          </tbody>
        </table>
      </div>
    </section>
    <section class="admin-panel-card" aria-labelledby="history-backups">
      <header class="admin-panel-head">
        <h2 id="history-backups">Backups</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Backups"><p>Before an import or a setup replaces a file, the old version is copied to this service's data folder, outside your vault. Each entry is one run, named by its time.</p></PanelHelp>
        </div>
      </header>
      <p v-if="!backups.length" class="admin-panel-text muted">No backups yet.</p>
      <ul v-else class="backups"><li v-for="b in backups" :key="b" class="mono">{{ b }}</li></ul>
    </section>
  </PageLayout>
</template>

<style scoped>
.mono { font-family: var(--mono); font-size: 0.8em; overflow-wrap: anywhere; }
.backups { margin: 0; padding: 12px 16px 12px 34px; }
</style>
