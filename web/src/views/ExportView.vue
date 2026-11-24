<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { vaultApi, type Item, type Vault } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import AdminSearch from "../components/admin/AdminSearch.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import FieldLabel from "../components/admin/FieldLabel.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import PageLayout from "../components/PageLayout.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** Pick a vault, narrow it with filters, tick items and download a .brainpack. Private items are listed apart and start unticked. */
const vaults = ref<Vault[]>([]);
const vaultId = ref("");
const blank = () => ({ paths: [] as string[], types: [] as string[], statuses: [] as string[], tags: [] as string[], created_from: "", created_to: "", modified_from: "", modified_to: "", changed_since_peer: "" });
const filter = reactive(blank());
/** Choices read from the vault itself, so nothing has to be typed. */
const opts = reactive({ folders: [] as string[], types: [] as string[], statuses: [] as string[], tags: [] as string[], peers: [] as string[], created: ["", ""], modified: ["", ""] });
const folderSearch = ref("");
const shownFolders = computed(() => opts.folders.filter((f) => f.toLowerCase().includes(folderSearch.value.trim().toLowerCase())));
const items = ref<Item[]>([]);
const ticked = ref(new Set<string>());
const search = ref("");
const loading = ref(false);
const exporting = ref(false);
const error = ref("");
const done = ref("");
const confirmOpen = ref(false);
const STARTER = ["AGENTS.md", "CLAUDE.md", "Templates/*", ".obsidian/*", "_setup/*", "00 Dashboard.md"];

const uniq = (xs: string[]) => [...new Set(xs.filter(Boolean))].sort((a, b) => a.localeCompare(b));
const day = (ts: number) => new Date(ts * 1000).toISOString().slice(0, 10);
const isOn = (list: string[], v: string) => list.includes(v);
function flip(list: string[], v: string, on?: boolean) {
  const i = list.indexOf(v);
  if (i < 0 && on !== false) list.push(v);
  else if (i >= 0 && on !== true) list.splice(i, 1);
}

/** Fill every choice from the vault's own notes. */
async function loadChoices() {
  Object.assign(filter, blank());
  items.value = [];
  if (!vaultId.value) return;
  try {
    const all = (await vaultApi.select(vaultId.value, { filter: {} })).all.filter((i) => !i.private);
    const folders: string[] = [];
    for (const i of all) {
      const parts = i.path.split("/").slice(0, -1);
      for (let n = 1; n <= Math.min(parts.length, 2); n++) folders.push(parts.slice(0, n).join("/"));
    }
    opts.folders = uniq(folders);
    opts.types = uniq(all.map((i) => i.type));
    opts.statuses = uniq(all.map((i) => i.status));
    opts.tags = uniq(all.flatMap((i) => i.tags));
    const created = all.map((i) => i.created).filter(Boolean).sort();
    const mod = all.map((i) => day(i.mtime)).sort();
    opts.created = [created[0] ?? "", created[created.length - 1] ?? ""];
    opts.modified = [mod[0] ?? "", mod[mod.length - 1] ?? ""];
    opts.peers = await vaultApi.peers(vaultId.value);
  } catch (err) {
    error.value = errorMessage(err);
  }
}
watch(vaultId, loadChoices);
const shareable = computed(() => items.value.filter((i) => !i.private && i.path.toLowerCase().includes(search.value.trim().toLowerCase())));
const privateItems = computed(() => items.value.filter((i) => i.private && i.path.toLowerCase().includes(search.value.trim().toLowerCase())));
const privateTicked = computed(() => items.value.filter((i) => i.private && ticked.value.has(i.path)).length);
const groups = computed(() => [
  { key: "types", title: "Types", help: "The type in a note's frontmatter. Nothing picked means all.", options: opts.types, list: filter.types },
  { key: "statuses", title: "Status", help: "The status in frontmatter. Nothing picked means all.", options: opts.statuses, list: filter.statuses },
  { key: "tags", title: "Tags", help: "A note matches when it has any picked tag.", options: opts.tags, list: filter.tags },
]);
const tickedCount = computed(() => ticked.value.size);

onMounted(async () => {
  try {
    vaults.value = await vaultApi.list();
    vaultId.value = vaults.value.find((v) => v.active)?.id ?? vaults.value[0]?.id ?? "";
    await loadChoices();
  } catch (err) {
    error.value = errorMessage(err);
  }
});

async function preview() {
  loading.value = true;
  error.value = done.value = "";
  try {
    const f = { paths: filter.paths.map((p) => (p.includes("*") || p.includes(".") ? p : `${p}/*`)), types: filter.types, statuses: filter.statuses, tags: filter.tags,
      created_from: filter.created_from.trim(), created_to: filter.created_to.trim(),
      modified_from: filter.modified_from.trim(), modified_to: filter.modified_to.trim(), changed_since_peer: filter.changed_since_peer.trim() };
    const r = await vaultApi.select(vaultId.value, { filter: f });
    items.value = r.all;
    ticked.value = new Set(r.selected);
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}

function tick(path: string, on: boolean) {
  if (on) ticked.value.add(path);
  else ticked.value.delete(path);
}

function ask() {
  if (!tickedCount.value) return;
  if (privateTicked.value) confirmOpen.value = true;
  else void doExport();
}

async function doExport() {
  confirmOpen.value = false;
  exporting.value = true;
  error.value = done.value = "";
  try {
    const include = items.value.filter((i) => !i.private && ticked.value.has(i.path)).map((i) => i.path);
    const include_private = items.value.filter((i) => i.private && ticked.value.has(i.path)).map((i) => i.path);
    const blob = await vaultApi.exportPack(vaultId.value, { use_filter: false, include, include_private });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${vaults.value.find((v) => v.id === vaultId.value)?.name ?? "vault"}.brainpack`;
    a.click();
    URL.revokeObjectURL(a.href);
    done.value = `Exported ${include.length + include_private.length} items.`;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    exporting.value = false;
  }
}
</script>

<template>
  <PageLayout class="admin-panel" title="Export" wide>
    <section class="admin-panel-card" aria-labelledby="export-filters">
      <header class="admin-panel-head">
        <h2 id="export-filters">What to export</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="What to export">
            <p>Choose a vault, narrow it with filters, then press Preview to list the matching notes. Untick what you do not want, then export a <code>.brainpack</code> file.</p>
            <p>Filters combine: a note must match every filled field. Empty fields match everything.</p>
          </PanelHelp>
        </div>
      </header>
      <div class="group fields">
        <div class="field">
          <FieldLabel title="Vault" for="x-vault"><p>The vault to export from.</p></FieldLabel>
          <select id="x-vault" v-model="vaultId"><option v-for="v in vaults" :key="v.id" :value="v.id">{{ v.name }}</option></select>
        </div>
        <div class="field wide">
          <FieldLabel title="Folders" for="x-folder-search"><p>Tick the folders to export. Nothing ticked means the whole vault. Starter preset ticks the structure files instead.</p></FieldLabel>
          <input id="x-folder-search" v-model="folderSearch" type="search" placeholder="Search folders" aria-label="Search folders" />
          <div class="checklist" role="group" aria-label="Folders">
            <ToggleSwitch v-for="f in shownFolders" :key="f" small :checked="isOn(filter.paths, f)" @change="flip(filter.paths, f, ($event.target as HTMLInputElement).checked)">{{ f }}</ToggleSwitch>
            <p v-if="!shownFolders.length" class="muted">No folders.</p>
          </div>
        </div>
        <div v-for="g in groups" :key="g.key" class="field">
          <FieldLabel :title="g.title"><p>{{ g.help }}</p></FieldLabel>
          <div class="chips" role="group" :aria-label="g.title">
            <button v-for="o in g.options" :key="o" type="button" class="chip" :class="{ on: isOn(g.list, o) }" :aria-pressed="isOn(g.list, o)" @click="flip(g.list, o)">{{ o }}</button>
            <span v-if="!g.options.length" class="muted">None in this vault.</span>
          </div>
        </div>
        <div class="field">
          <FieldLabel title="Created from" for="x-cf"><p>Earliest <code>created</code> date. Limited to the dates in this vault.</p></FieldLabel>
          <input id="x-cf" v-model="filter.created_from" type="date" :min="opts.created[0]" :max="opts.created[1]" />
        </div>
        <div class="field">
          <FieldLabel title="Created to" for="x-ct"><p>Latest <code>created</code> date.</p></FieldLabel>
          <input id="x-ct" v-model="filter.created_to" type="date" :min="opts.created[0]" :max="opts.created[1]" />
        </div>
        <div class="field">
          <FieldLabel title="Modified from" for="x-mf"><p>Earliest file change date.</p></FieldLabel>
          <input id="x-mf" v-model="filter.modified_from" type="date" :min="opts.modified[0]" :max="opts.modified[1]" />
        </div>
        <div class="field">
          <FieldLabel title="Modified to" for="x-mt"><p>Latest file change date.</p></FieldLabel>
          <input id="x-mt" v-model="filter.modified_to" type="date" :min="opts.modified[0]" :max="opts.modified[1]" />
        </div>
        <div class="field">
          <FieldLabel title="Changed since device" for="x-peer"><p>Lists only what changed since you last synced with that device. Devices appear here after a first import.</p></FieldLabel>
          <select id="x-peer" v-model="filter.changed_since_peer"><option value="">Any time</option><option v-for="p in opts.peers" :key="p" :value="p">{{ p }}</option></select>
        </div>
        <div class="actions">
          <button type="button" class="chip" @click="filter.paths = [...STARTER]">Starter preset</button>
          <button type="button" class="primary" :disabled="loading || !vaultId" :aria-busy="loading" @click="preview">Preview</button>
        </div>
      </div>
    </section>

    <section v-if="items.length" class="admin-panel-card" aria-labelledby="export-items">
      <header class="admin-panel-head">
        <h2 id="export-items">Items</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Items"><p>Tick the notes to put in the pack. Private notes are listed apart and start unticked: tick one to include it.</p></PanelHelp>
          <button type="button" class="primary" :disabled="!tickedCount || exporting" :aria-busy="exporting" @click="ask">Export {{ tickedCount }}</button>
          <AdminSearch v-model="search" label="Search items" />
        </div>
      </header>
      <ActionMessage v-if="done" kind="ok" :text="done" class="admin-panel-text" />
      <div class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="export-items">
        <table class="admin-records">
          <thead><tr><th scope="col">Include</th><th scope="col">Path</th><th scope="col">Type</th><th scope="col">Status</th></tr></thead>
          <tbody>
            <tr v-for="i in shareable" :key="i.path">
              <td><ToggleSwitch small :checked="ticked.has(i.path)" :aria-label="`Include ${i.path}`" @change="tick(i.path, ($event.target as HTMLInputElement).checked)" /></td>
              <th scope="row" class="mono">{{ i.path }}</th><td>{{ i.type }}</td><td>{{ i.status }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <h3 class="group-title">Private items</h3>
      <p class="admin-panel-text muted">Off by default. A private note only leaves this device when you tick it here.</p>
      <p v-if="!privateItems.length" class="admin-panel-text muted">None.</p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-label="Private items">
        <table class="admin-records">
          <tbody>
            <tr v-for="i in privateItems" :key="i.path">
              <td><ToggleSwitch small :checked="ticked.has(i.path)" :aria-label="`Include private ${i.path}`" @change="tick(i.path, ($event.target as HTMLInputElement).checked)" /></td>
              <th scope="row" class="mono">{{ i.path }} <span class="status-pill">Private</span></th>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text" />

    <ConfirmModal :open="confirmOpen" title="Include private notes?" :message="`${privateTicked} private note(s) will go into the pack and can be read by whoever gets the file.`" confirm-label="Export" @confirm="doExport" @close="confirmOpen = false" />
  </PageLayout>
</template>

<style scoped>
.group.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px 20px; padding: 20px 16px; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > :is(input, select) { min-height: 44px; width: 100%; }
.field.wide { grid-column: 1 / -1; }
.checklist { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 6px 16px; max-height: 200px; overflow: auto; padding: 8px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; max-height: 120px; overflow: auto; }
.chip.on { border-color: var(--accent); color: var(--accent); }
.actions { grid-column: 1 / -1; display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.group-title { margin: 16px 16px 0; font-size: 1em; }
.mono { font-family: var(--mono); font-size: 0.85em; overflow-wrap: anywhere; font-weight: 400; }
.status-pill { padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; font-family: var(--sans); }
</style>
