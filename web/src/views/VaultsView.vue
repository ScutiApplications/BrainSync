<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { vaultApi, type Vault } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import AdminSearch from "../components/admin/AdminSearch.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import RecordDrawer from "../components/admin/RecordDrawer.vue";
import PageLayout from "../components/PageLayout.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** The vaults BrainSync knows. Registering a vault never changes it; "Create" only makes a missing or empty folder. */
const vaults = ref<Vault[]>([]);
const loading = ref(true);
const listError = ref("");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const visible = computed(() => {
  const q = search.value.trim().toLowerCase();
  return vaults.value.filter((v) => !q || v.name.toLowerCase().includes(q) || v.path.toLowerCase().includes(q));
});

const selectedId = ref<string | null>(null);
const selected = computed(() => vaults.value.find((v) => v.id === selectedId.value) ?? null);
const editing = ref(false);
const draftFolders = ref("");
const drawer = ref<InstanceType<typeof RecordDrawer>>();
const busy = ref(false);
const actionError = ref("");
const removeOpen = ref(false);

const createOpen = ref(false);
const name = ref("");
const path = ref("");
const createFolder = ref(false);
const createError = ref("");

async function load() {
  loading.value = true;
  listError.value = "";
  try {
    vaults.value = await vaultApi.list();
  } catch (err) {
    listError.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function open(v: Vault) {
  selectedId.value = v.id;
  editing.value = false;
  actionError.value = "";
}

function startEdit() {
  draftFolders.value = selected.value?.private_folders.join("\n") ?? "";
  editing.value = true;
}

async function run(task: () => Promise<void>) {
  busy.value = true;
  actionError.value = "";
  try {
    await task();
    await load();
  } catch (err) {
    actionError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

const saveFolders = () => run(async () => {
  await vaultApi.setPrivateFolders(selected.value!.id, draftFolders.value.split("\n"));
  editing.value = false;
});
const makeActive = () => run(() => vaultApi.setActive(selected.value!.id).then(() => undefined));
const remove = () => run(async () => {
  await vaultApi.remove(selected.value!.id);
  removeOpen.value = false;
  selectedId.value = null;
});

function openCreate() {
  name.value = path.value = createError.value = "";
  createFolder.value = false;
  createOpen.value = true;
}

async function create() {
  busy.value = true;
  createError.value = "";
  try {
    await vaultApi.add(name.value, path.value, createFolder.value);
    createOpen.value = false;
    await load();
  } catch (err) {
    createError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <PageLayout class="admin-panel" title="Vaults" wide>
    <section class="admin-panel-card" aria-labelledby="vault-roster">
      <header class="admin-panel-head">
        <h2 id="vault-roster">Vaults</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Vaults">
            <p>The Brain vaults on this computer that BrainSync can export from, import into and share. Open one to see its folder, mark private folders or remove it from the list.</p>
            <p>The <b>active</b> vault is the one the Claude Code and Codex hooks use. Removing a vault from the list never deletes its files.</p>
          </PanelHelp>
          <button type="button" class="admin-icon accent" aria-label="Add vault" title="Add vault" @click="openCreate">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          </button>
          <AdminSearch ref="searchField" v-model="search" label="Search vaults" />
        </div>
      </header>
      <ActionMessage v-if="listError" kind="error" :text="listError" class="admin-panel-text"><button type="button" class="chip" @click="load">Retry</button></ActionMessage>
      <p v-else-if="loading" class="admin-panel-text muted" role="status">Loading vaults…</p>
      <p v-else-if="!vaults.length" class="admin-panel-text muted">No vaults yet. Add one with the plus button.</p>
      <p v-else-if="!visible.length" class="admin-panel-text muted">No vaults match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="vault-roster">
        <table class="admin-records">
          <thead><tr><th scope="col">Name</th><th scope="col">Folder</th><th scope="col">Private folders</th><th scope="col">Status</th></tr></thead>
          <tbody>
            <tr v-for="v in visible" :key="v.id" :class="{ selected: v.id === selectedId }">
              <th scope="row"><button type="button" class="admin-row-button" aria-haspopup="dialog" @click="open(v)">{{ v.name }}</button></th>
              <td class="mono">{{ v.path }}</td>
              <td>{{ v.private_folders.length }}</td>
              <td><span v-if="v.active" class="status-pill success">Active</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!loading && !listError && vaults.length" class="admin-panel-text muted count" role="status">{{ visible.length }} of {{ vaults.length }} vaults</p>
    </section>

    <RecordDrawer ref="drawer" :open="selected !== null" :title="selected?.name ?? 'Vault'" editable :editing="editing" :busy="busy"
      :fallback-focus="() => searchField?.focus()" @edit="startEdit" @close="selectedId = null" @discard="editing = false" @save="saveFolders">
      <div v-if="selected" class="admin-details">
        <dl>
          <dt>Folder</dt><dd class="mono">{{ selected.path }}</dd>
          <dt>Status</dt><dd>{{ selected.active ? "Active: the agent hooks use this vault" : "Not active" }}</dd>
        </dl>
        <form v-if="editing" id="vault-edit" class="admin-editor" @submit.prevent="drawer?.requestSave()">
          <label for="private-folders">Private folders (one per line)</label>
          <textarea id="private-folders" v-model="draftFolders" rows="5" :disabled="busy" spellcheck="false"></textarea>
          <p class="muted">Notes in these folders are private: never shared or exported unless you tick them one by one.</p>
        </form>
        <template v-else>
          <h4>Private folders</h4>
          <p v-if="!selected.private_folders.length" class="muted">None. A note is also private when its frontmatter says <code>private: true</code>.</p>
          <ul v-else class="folder-list"><li v-for="f in selected.private_folders" :key="f" class="mono">{{ f }}</li></ul>
          <ToggleSwitch v-if="!selected.active" :checked="false" :disabled="busy" @change="makeActive">Make this the active vault</ToggleSwitch>
        </template>
        <ActionMessage v-if="actionError" kind="error" :text="actionError" />
        <section class="danger-zone">
          <h4>Danger zone</h4>
          <p class="muted">Removes the vault from this list. Its files and notes stay where they are.</p>
          <button type="button" class="danger" :disabled="busy" @click="removeOpen = true">Remove from list</button>
        </section>
      </div>
      <template v-if="editing" #footer>
        <button type="button" class="chip" :disabled="busy" @click="drawer?.requestCancel()">Cancel</button>
        <button type="button" class="primary" :disabled="busy" :aria-busy="busy" @click="drawer?.requestSave()">Save</button>
      </template>
    </RecordDrawer>

    <RecordDrawer :open="createOpen" title="Add vault" :editing="name.trim() !== '' || path.trim() !== ''" :busy="busy" save-label="Add vault"
      :fallback-focus="() => searchField?.focus()" @close="createOpen = false" @discard="createOpen = false" @save="create">
      <form id="vault-create" class="admin-editor" @submit.prevent="create">
        <label for="vault-name">Name</label>
        <input id="vault-name" v-model="name" type="text" required :disabled="busy" />
        <label for="vault-path">Folder</label>
        <input id="vault-path" v-model="path" type="text" required spellcheck="false" placeholder="D:\Notes\Brain" :disabled="busy" />
        <ToggleSwitch v-model="createFolder" :disabled="busy">Create the folder (new or empty only)</ToggleSwitch>
        <p class="muted">Without this the folder must already be a Brain vault: it needs <code>.obsidian</code> and <code>AGENTS.md</code>.</p>
        <ActionMessage v-if="createError" kind="error" :text="createError" />
      </form>
      <template #footer>
        <button type="submit" form="vault-create" class="primary" :disabled="busy" :aria-busy="busy">Add vault</button>
      </template>
    </RecordDrawer>

    <ConfirmModal :open="removeOpen" title="Remove vault from the list?" message="Its files and notes are not touched. Saved sync history with other devices is dropped." confirm-label="Remove" danger :busy="busy"
      @confirm="remove" @close="removeOpen = false" />
  </PageLayout>
</template>

<style scoped>
.mono { font-family: var(--mono); font-size: 0.85em; overflow-wrap: anywhere; }
.folder-list { margin: 0; padding-inline-start: 18px; }
.status-pill { padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; }
.status-pill.success { border-color: color-mix(in srgb, var(--success) 55%, var(--border)); color: var(--success); }
</style>
