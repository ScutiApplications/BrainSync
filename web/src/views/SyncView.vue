<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { agentApi, vaultApi, type AgentStatus, type JobView, type SyncProject, type Vault } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import AdminSearch from "../components/admin/AdminSearch.vue";
import FieldLabel from "../components/admin/FieldLabel.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import RecordDrawer from "../components/admin/RecordDrawer.vue";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** List the git projects on this computer and have Claude Code or Codex update their notes in the vault (the project-sync skill). */
const route = useRoute();
const vaults = ref<Vault[]>([]);
const vaultId = ref("");
const root = ref("");
const projects = ref<SyncProject[]>([]);
const agents = ref<AgentStatus | null>(null);
const loading = ref(true);
const error = ref("");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();

const visible = computed(() => {
  const q = search.value.trim().toLowerCase();
  return projects.value.filter((p) => !q || p.rel.toLowerCase().includes(q));
});
const usable = computed(() => (["claude", "codex"] as const).filter((k) => agents.value?.[k].runnable && agents.value?.[k].enabled));
const LABEL: Record<string, string> = { claude: "Claude Code", codex: "Codex" };

const project = ref<SyncProject | null>(null);
const agent = ref("");
const job = ref<JobView | null>(null);
const starting = ref(false);
const runError = ref("");
let timer: ReturnType<typeof setInterval> | undefined;

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const r = await agentApi.projects(vaultId.value);
    root.value = r.root;
    projects.value = r.projects;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    vaults.value = await vaultApi.list();
    const asked = typeof route.query.vault === "string" ? route.query.vault : "";
    vaultId.value = vaults.value.find((v) => v.id === asked)?.id ?? vaults.value.find((v) => v.active)?.id ?? vaults.value[0]?.id ?? "";
    agents.value = await agentApi.status();
    if (vaultId.value) await load();
    else loading.value = false;
  } catch (err) {
    error.value = errorMessage(err);
    loading.value = false;
  }
});
watch(vaultId, (v, old) => { if (old && v) void load(); });
onBeforeUnmount(() => clearInterval(timer));

function open(p: SyncProject) {
  project.value = p;
  job.value = null;
  runError.value = "";
  const def = agents.value?.default ?? "";
  agent.value = usable.value.includes(def as "claude") ? def : (usable.value[0] ?? "");
}

function close() {
  project.value = null;
  clearInterval(timer);
}

async function poll() {
  if (!job.value) return;
  try {
    job.value = await agentApi.job(job.value.id);
    if (job.value.state !== "running") {
      clearInterval(timer);
      await load();
    }
  } catch (err) {
    clearInterval(timer);
    runError.value = errorMessage(err);
  }
}

async function run() {
  if (!project.value || !agent.value) return;
  starting.value = true;
  runError.value = "";
  try {
    job.value = await agentApi.run(vaultId.value, project.value.rel, agent.value);
    clearInterval(timer);
    timer = setInterval(poll, 1500);
  } catch (err) {
    runError.value = errorMessage(err);
  } finally {
    starting.value = false;
  }
}

async function cancel() {
  if (!job.value) return;
  try {
    await agentApi.cancel(job.value.id);
    await poll();
  } catch (err) {
    runError.value = errorMessage(err);
  }
}

const running = computed(() => job.value?.state === "running");
const STATE: Record<string, string> = { running: "Running", done: "Finished", failed: "Failed", cancelled: "Cancelled", timeout: "Stopped: time limit" };
</script>

<template>
  <PageLayout class="admin-panel" title="Sync notes" wide>
    <section class="admin-panel-card" aria-labelledby="sync-list">
      <header class="admin-panel-head">
        <h2 id="sync-list">Projects</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Sync notes">
            <p>Updates the note of a code project in your vault (<code>Projects/&lt;name&gt;.md</code>) from its code, README and recent git history, using the <b>project-sync</b> skill.</p>
            <p>Claude Code or Codex does the work on this computer. It may edit the vault only; the project's code is read-only. Run Agent setup first so the skill is installed.</p>
          </PanelHelp>
          <button type="button" class="admin-icon" aria-label="Refresh projects" title="Refresh projects" :disabled="loading || !vaultId" :aria-busy="loading" @click="load">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 0 1 14-5.3M20 4v4h-4M20 12a8 8 0 0 1-14 5.3M4 20v-4h4" /></svg>
          </button>
          <AdminSearch ref="searchField" v-model="search" label="Search projects" />
        </div>
      </header>
      <div class="bar">
        <div class="field">
          <FieldLabel title="Vault" for="y-vault"><p>The vault whose project notes are updated.</p></FieldLabel>
          <select id="y-vault" v-model="vaultId"><option v-for="v in vaults" :key="v.id" :value="v.id">{{ v.name }}</option></select>
        </div>
        <p v-if="root" class="muted path">Looking in {{ root }}. Change the folder in Settings → Agents.</p>
      </div>
      <ActionMessage v-if="agents && !usable.length" kind="warning" class="admin-panel-text"
        text="No agent can run. Install Claude Code or Codex, or switch one on in Settings → Agents." />
      <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text" />
      <p v-else-if="loading" class="admin-panel-text muted" role="status">Looking for projects…</p>
      <p v-else-if="!vaults.length" class="admin-panel-text muted">No vault yet. Add one on the Vaults page.</p>
      <p v-else-if="!projects.length" class="admin-panel-text muted">No git projects found in that folder.</p>
      <p v-else-if="!visible.length" class="admin-panel-text muted">No projects match your search.</p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="sync-list">
        <table class="admin-records">
          <thead><tr><th scope="col">Project</th><th scope="col">Note</th><th scope="col">Last synced</th></tr></thead>
          <tbody>
            <tr v-for="p in visible" :key="p.rel" :class="{ selected: project?.rel === p.rel }">
              <th scope="row"><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="open(p)">{{ p.rel }}</button></th>
              <td>{{ p.note ? "Has a note" : "No note yet" }}</td>
              <td>{{ p.last_synced || "Never" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <RecordDrawer :open="project !== null" :title="project ? `Sync ${project.name}` : 'Sync'" :editing="running" :busy="running"
      :fallback-focus="() => searchField?.focus()" @close="close" @discard="close">
      <div v-if="project" class="drawer">
        <p class="muted">Updates <code>Projects/{{ project.name }}.md</code> in the vault from <span class="mono">{{ project.path }}</span>. The code is only read.</p>
        <div v-if="!job" class="agents">
          <FieldLabel title="Agent" bare><p>Which agent does the sync. Only agents that are installed and switched on are listed.</p></FieldLabel>
          <div class="chips" role="group" aria-label="Agent">
            <button v-for="k in usable" :key="k" type="button" class="chip" :class="{ on: agent === k }" :aria-pressed="agent === k" @click="agent = k">{{ LABEL[k] }}</button>
          </div>
          <ActionMessage v-if="!usable.length" kind="warning" text="No agent can run. See Settings → Agents." />
        </div>
        <template v-else>
          <p><span class="status-pill" :class="job.state">{{ STATE[job.state] }}</span> <span class="muted">with {{ LABEL[job.agent] }}</span></p>
          <pre class="out" aria-live="polite">{{ job.output || "Waiting for output…" }}</pre>
        </template>
        <ActionMessage v-if="runError" kind="error" :text="runError" />
      </div>
      <template #footer>
        <button v-if="running" type="button" class="danger" @click="cancel">Cancel run</button>
        <button v-else-if="job" type="button" class="chip" @click="close">Close</button>
        <button v-if="!job" type="button" class="primary" :disabled="starting || !agent" :aria-busy="starting" @click="run">Run sync</button>
      </template>
    </RecordDrawer>
  </PageLayout>
</template>

<style scoped>
.bar { display: grid; grid-template-columns: minmax(220px, 320px) 1fr; gap: 12px 20px; align-items: end; padding: 16px; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > select { min-height: 44px; width: 100%; }
.muted { color: var(--muted); }
.path { margin: 0; font-size: 0.85em; overflow-wrap: anywhere; }
.mono { font-family: var(--mono); font-size: 0.85em; overflow-wrap: anywhere; }
.drawer { display: grid; gap: 16px; }
.drawer p { margin: 0; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip.on { border-color: var(--accent); color: var(--accent); }
.out { margin: 0; max-height: 360px; overflow: auto; padding: 10px; border-radius: var(--radius-md); background: var(--code-bg); font: 0.8em var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; scrollbar-gutter: stable; }
.status-pill { padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; }
.status-pill.done { border-color: color-mix(in srgb, var(--success) 55%, var(--border)); color: var(--success); }
.status-pill.failed, .status-pill.timeout { border-color: var(--danger); color: var(--danger); }
</style>
