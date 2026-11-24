<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { importApi, peerApi, vaultApi, type ApplyResult, type Decision, type Item, type Preview, type PreviewRow, type Vault } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import FieldLabel from "../components/admin/FieldLabel.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import RecordDrawer from "../components/admin/RecordDrawer.vue";
import PageLayout from "../components/PageLayout.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** Bring notes in from a pack file or from a device that is sharing. Nothing is written until Apply. */
const OPTIONS: Record<string, string[]> = {
  new: ["import", "skip"], theirs_only: ["import", "skip"], identical: ["skip"], mine_only: ["skip", "theirs"],
  conflict: ["merge", "mine", "theirs", "both", "skip"], no_base: ["merge", "mine", "theirs", "both", "skip"],
};
const STATE_TEXT: Record<string, string> = {
  new: "New here", identical: "Same on both", theirs_only: "Changed there only", mine_only: "Changed here only",
  conflict: "Changed on both", no_base: "Differs, first sync",
};

const vaults = ref<Vault[]>([]);
const targetId = ref("");
const file = ref<File | null>(null);
const dragging = ref(false);
function pickFile(f: File | null | undefined) {
  file.value = f ?? null;
}
function dropFile(e: DragEvent) {
  dragging.value = false;
  pickFile(e.dataTransfer?.files[0]);
}
const preview = ref<Preview | null>(null);
const actions = reactive<Record<string, string>>({});
const choices = reactive<Record<string, Record<string, string>>>({});
const activePath = ref<string | null>(null);
const active = computed<PreviewRow | null>(() => preview.value?.rows.find((r) => r.path === activePath.value) ?? null);
const busy = ref(false);
const error = ref("");
const result = ref<ApplyResult | null>(null);

const address = ref("");
const code = ref("");
const cid = ref("");
const peerName = ref("");
const peerVaults = ref<{ id: string; name: string }[]>([]);
const peerVaultId = ref("");
const peerItems = ref<Item[]>([]);
const peerTicked = ref(new Set<string>());

onMounted(async () => {
  try {
    vaults.value = await vaultApi.list();
    targetId.value = vaults.value.find((v) => v.active)?.id ?? vaults.value[0]?.id ?? "";
  } catch (err) {
    error.value = errorMessage(err);
  }
});
onUnmounted(() => { if (cid.value) void peerApi.close(cid.value).catch(() => {}); });

function options(r: PreviewRow): string[] {
  let o = [...(OPTIONS[r.state] ?? ["skip"])];
  if (r.binary) o = o.filter((x) => x !== "merge");
  else if (/(^|\/)(index|log)\.md$/.test(r.path) && r.state !== "new") o.push("union");
  return o;
}

function adopt(p: Preview) {
  preview.value = p;
  result.value = null;
  for (const k of Object.keys(actions)) delete actions[k];
  for (const k of Object.keys(choices)) delete choices[k];
  for (const r of p.rows) actions[r.path] = r.default === "unresolved" ? "skip" : r.default;
}

async function guard(task: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await task();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

const upload = () => guard(async () => {
  if (!file.value) throw new Error("Choose a pack file first.");
  adopt(await importApi.upload(targetId.value, file.value));
});

const connect = () => guard(async () => {
  if (cid.value) await peerApi.close(cid.value).catch(() => {});
  const c = await peerApi.connect(address.value, code.value);
  cid.value = c.cid;
  peerName.value = c.name;
  peerVaults.value = await peerApi.vaults(c.cid);
  peerVaultId.value = peerVaults.value[0]?.id ?? "";
  peerItems.value = [];
});

const listPeer = () => guard(async () => {
  const m = await peerApi.manifest(cid.value, peerVaultId.value);
  peerItems.value = m.items;
  peerTicked.value = new Set(m.items.filter((i) => !i.private).map((i) => i.path));
});

function tickPeer(path: string, on: boolean) {
  if (on) peerTicked.value.add(path);
  else peerTicked.value.delete(path);
}

const pull = () => guard(async () => {
  adopt(await peerApi.pull(cid.value, peerVaultId.value, [...peerTicked.value], targetId.value));
});

function pick(path: string, hunk: number, value: string) {
  (choices[path] ??= {})[String(hunk)] = value;
}

const apply = () => guard(async () => {
  if (!preview.value) return;
  const decisions: Record<string, Decision> = {};
  for (const r of preview.value.rows) {
    const action = actions[r.path];
    if (action && action !== "skip") decisions[r.path] = { action, choices: choices[r.path] ?? {} };
  }
  result.value = await importApi.apply(targetId.value, preview.value.pack_id, decisions);
  preview.value = null;
});

const conflicts = (r: PreviewRow) => (r.hunks ?? []).filter((h) => h.kind === "conflict");
</script>

<template>
  <PageLayout class="admin-panel" title="Import" wide>
    <section class="admin-panel-card" aria-labelledby="import-source">
      <header class="admin-panel-head">
        <h2 id="import-source">Where from</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Where from">
            <p>Import into one of your vaults, from a <code>.brainpack</code> file or from another device that is sharing right now. You see a preview first; nothing changes until you press Apply.</p>
            <p>Notes missing from the source are left alone: import never deletes.</p>
          </PanelHelp>
        </div>
      </header>
      <div class="group fields">
        <div class="field">
          <FieldLabel title="Into vault" for="i-vault"><p>The vault that receives the notes.</p></FieldLabel>
          <select id="i-vault" v-model="targetId"><option v-for="v in vaults" :key="v.id" :value="v.id">{{ v.name }}</option></select>
        </div>
        <div class="field">
          <FieldLabel title="Pack file" for="i-file"><p>A <code>.brainpack</code> file made by Export on another device.</p></FieldLabel>
          <label :class="['drop', { over: dragging }]" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="dropFile">
            <input id="i-file" type="file" accept=".brainpack" class="file-input" @change="pickFile(($event.target as HTMLInputElement).files?.[0])" />
            <span v-if="!file" class="muted">Drop a .brainpack here or choose one</span>
            <span v-else class="mono">{{ file.name }}</span>
          </label>
        </div>
        <div class="actions"><button type="button" class="primary" :disabled="busy || !targetId" :aria-busy="busy" @click="upload">Preview pack</button></div>
      </div>
      <div class="group fields">
        <h3 class="wide-row">From a device on this network</h3>
        <div class="field">
          <FieldLabel title="Address" for="i-addr"><p>The other device's IPv4 address and port, for example <code>192.168.1.20:26508</code>. Only addresses on your own network are accepted.</p></FieldLabel>
          <input id="i-addr" v-model="address" type="text" spellcheck="false" placeholder="192.168.1.20:26508" />
        </div>
        <div class="field">
          <FieldLabel title="Pairing code" for="i-code"><p>The 8-character code shown on the other device's Share page while it is sharing.</p></FieldLabel>
          <input id="i-code" v-model="code" type="text" spellcheck="false" autocomplete="off" />
        </div>
        <div class="actions"><button type="button" class="primary" :disabled="busy || !address || !code" :aria-busy="busy" @click="connect">Connect</button></div>
        <template v-if="cid">
          <p class="wide-row"><ActionMessage kind="ok" :text="`Connected to ${peerName}.`" /></p>
          <div class="field">
            <FieldLabel title="Their vault" for="i-pvault"><p>A vault the other device is sharing.</p></FieldLabel>
            <select id="i-pvault" v-model="peerVaultId"><option v-for="v in peerVaults" :key="v.id" :value="v.id">{{ v.name }}</option></select>
          </div>
          <div class="actions"><button type="button" class="chip" :disabled="busy || !peerVaultId" @click="listPeer">List shared items</button></div>
        </template>
      </div>
      <div v-if="peerItems.length" class="admin-table-scroll" tabindex="0" role="region" aria-label="Shared items">
        <table class="admin-records">
          <thead><tr><th scope="col">Pull</th><th scope="col">Path</th></tr></thead>
          <tbody>
            <tr v-for="i in peerItems" :key="i.path">
              <td><ToggleSwitch small :checked="peerTicked.has(i.path)" :aria-label="`Pull ${i.path}`" @change="tickPeer(i.path, ($event.target as HTMLInputElement).checked)" /></td>
              <th scope="row" class="mono">{{ i.path }} <span v-if="i.private" class="status-pill">Private</span></th>
            </tr>
          </tbody>
        </table>
        <p class="admin-panel-text"><button type="button" class="primary" :disabled="busy || !peerTicked.size" :aria-busy="busy" @click="pull">Preview {{ peerTicked.size }} items</button></p>
      </div>
    </section>

    <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text" />
    <ActionMessage v-if="result" kind="ok" class="admin-panel-text"
      :text="`Applied ${result.applied.length}, skipped ${result.skipped.length}.${result.backup ? ` Old versions saved as backup ${result.backup}.` : ''}`" />

    <section v-if="preview" class="admin-panel-card" aria-labelledby="import-preview">
      <header class="admin-panel-head">
        <h2 id="import-preview">Preview from {{ preview.vault_name }}</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Preview">
            <p>Each row says how the note differs and what Apply will do. Changed on both sides: open it to choose, per conflict, your version, theirs or both. Rows set to skip are not touched.</p>
          </PanelHelp>
          <button type="button" class="primary" :disabled="busy" :aria-busy="busy" @click="apply">Apply</button>
        </div>
      </header>
      <div class="admin-table-scroll" tabindex="0" role="region" aria-labelledby="import-preview">
        <table class="admin-records">
          <thead><tr><th scope="col">Note</th><th scope="col">Difference</th><th scope="col">Action</th></tr></thead>
          <tbody>
            <tr v-for="r in preview.rows" :key="r.path">
              <th scope="row" class="mono">{{ r.path }} <span v-if="r.private" class="status-pill">Private</span> <span v-if="r.binary" class="status-pill">Binary</span></th>
              <td>
                {{ STATE_TEXT[r.state] ?? r.state }}
                <button v-if="conflicts(r).length" type="button" class="chip" @click="activePath = r.path">{{ conflicts(r).length }} conflict(s)</button>
              </td>
              <td>
                <select v-model="actions[r.path]" :aria-label="`Action for ${r.path}`">
                  <option v-for="o in options(r)" :key="o" :value="o">{{ o }}</option>
                </select>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <RecordDrawer :open="active !== null" :title="active?.path ?? 'Conflicts'" @close="activePath = null">
      <div v-if="active" class="admin-details">
        <p class="muted">Pick what each conflict becomes, then set this note's action to <b>merge</b>.</p>
        <section v-for="(h, i) in conflicts(active)" :key="i" class="hunk">
          <h4>Conflict {{ i + 1 }}</h4>
          <b>Yours</b><pre>{{ (h.mine ?? []).join("") || "(nothing)" }}</pre>
          <b>Theirs</b><pre>{{ (h.theirs ?? []).join("") || "(nothing)" }}</pre>
          <div class="choice" role="group" :aria-label="`Result of conflict ${i + 1}`">
            <button v-for="c in ['mine', 'theirs', 'both']" :key="c" type="button" class="chip" :aria-pressed="choices[active.path]?.[String(i)] === c" @click="pick(active.path, i, c)">{{ c }}</button>
          </div>
        </section>
      </div>
    </RecordDrawer>
  </PageLayout>
</template>

<style scoped>
.group.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px 20px; padding: 20px 16px; }
.group.fields + .group.fields { border-top: 1px solid var(--border); }
.field { display: grid; gap: 4px; min-width: 0; }
.field > :is(input, select) { min-height: 44px; width: 100%; }
.drop { display: flex; align-items: center; min-height: 44px; padding: 8px 10px; border: 1px dashed var(--border); border-radius: var(--radius-md); font-size: 0.9em; cursor: pointer; position: relative; }
.drop.over { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, var(--surface)); }
.drop:focus-within { border-style: solid; border-color: var(--accent); }
.file-input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
.actions { grid-column: 1 / -1; display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.wide-row { grid-column: 1 / -1; margin: 0; }
h3.wide-row { padding-bottom: 8px; border-bottom: 1px solid var(--border); font-size: 1em; }
.mono { font-family: var(--mono); font-size: 0.85em; overflow-wrap: anywhere; font-weight: 400; }
.status-pill { padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; font-family: var(--sans); }
.hunk { display: grid; gap: 6px; padding: 10px 0; border-top: 1px solid var(--border); }
.hunk pre { margin: 0; padding: 8px; overflow: auto; border-radius: var(--radius-md); background: var(--code-bg); font: 0.85em var(--mono); white-space: pre-wrap; scrollbar-gutter: stable; }
.choice { display: flex; gap: 6px; }
.choice .chip[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
</style>
