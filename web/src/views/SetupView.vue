<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { fsApi, setupApi, vaultApi, type SetupBody, type SetupOp, type SetupResult, type VerifyRow, type Vault } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import FieldLabel from "../components/admin/FieldLabel.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import PageLayout from "../components/PageLayout.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** Make Claude Code and Codex use a vault. Three steps: choose, review the changes, apply. Nothing is written before Apply. */
const vaults = ref<Vault[]>([]);
const vaultId = ref("");
const projectsRoot = ref("");
const claude = ref(true);
const codex = ref(true);
const found = ref({ claude: true, codex: true });
const intro = ref(true);
const ops = ref<SetupOp[]>([]);
const on = ref(new Set<number>());
const results = ref<SetupResult[]>([]);
const rows = ref<VerifyRow[]>([]);
const busy = ref(false);
const picking = ref(false);
const error = ref("");
const confirmOpen = ref(false);

const vault = computed(() => vaults.value.find((v) => v.id === vaultId.value) ?? null);
const body = computed<SetupBody>(() => ({ vault_id: vaultId.value, projects_root: projectsRoot.value, claude: claude.value, codex: codex.value, selected: [...on.value] }));
/** 0 = read first, 1 = choose, 2 = review, 3 = done. */
const step = computed(() => (results.value.length ? 3 : ops.value.length ? 2 : intro.value ? 0 : 1));
const changes = computed(() => ops.value.filter((o) => !o.manual));
const manual = computed(() => ops.value.filter((o) => o.manual));
const hasDiff = (o: SetupOp) => o.diff.trim() !== "";

const WILL_DO = [
  ["Skills", "Copied to ~/.claude/skills (process inbox, weekly review, project sync...). Both agents use them."],
  ["Claude Code", "Hooks that keep the vault tidy and committed, a merge into ~/.claude/settings.json (your own entries stay, a backup is kept) and a marked block in ~/.claude/CLAUDE.md."],
  ["Codex", "A marked block in ~/.codex/AGENTS.md, links to the skills and the vault added as a writable folder."],
  ["Git", "If the vault is not a git repo yet, it is initialised. No remote is added."],
];

onMounted(async () => {
  try {
    vaults.value = await vaultApi.list();
    vaultId.value = vaults.value.find((v) => v.active)?.id ?? vaults.value[0]?.id ?? "";
    found.value = await setupApi.detect();
    // Tick what is installed here; if neither is found, tick both.
    claude.value = found.value.claude || !found.value.codex;
    codex.value = found.value.codex || !found.value.claude;
  } catch (err) {
    error.value = errorMessage(err);
  }
});

/** The projects folder is usually the folder that holds the vault, so start there. */
watch(vault, (v, old) => {
  if (v && (!projectsRoot.value || projectsRoot.value === parentOf(old?.path))) projectsRoot.value = parentOf(v.path);
  ops.value = [];
  results.value = [];
  rows.value = [];
});
function parentOf(p?: string) {
  if (!p) return "";
  const cut = p.replace(/[\\/]+$/, "").split(/[\\/]/);
  cut.pop();
  return cut.join("\\");
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

const plan = () => guard(async () => {
  results.value = rows.value = [];
  ops.value = await setupApi.plan(body.value);
  on.value = new Set(ops.value.filter((o) => !o.manual).map((o) => o.id));
});

const apply = () => guard(async () => {
  confirmOpen.value = false;
  results.value = await setupApi.apply(body.value);
  ops.value = [];
});

const verify = () => guard(async () => {
  rows.value = await setupApi.verify(body.value);
});

function back() {
  ops.value = [];
  results.value = [];
  intro.value = false;
}

async function browse() {
  picking.value = true;
  try {
    const { path } = await fsApi.pick();
    if (path) projectsRoot.value = path;
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    picking.value = false;
  }
}

function flip(id: number, checked: boolean) {
  if (checked) on.value.add(id);
  else on.value.delete(id);
}
</script>

<template>
  <PageLayout class="admin-panel" title="Agent setup" wide>
    <ol class="steps" aria-label="Progress">
      <li :class="{ now: step === 0, done: step > 0 }"><span>0</span> Read first</li>
      <li :class="{ now: step === 1, done: step > 1 }"><span>1</span> Choose</li>
      <li :class="{ now: step === 2, done: step > 2 }"><span>2</span> Review changes</li>
      <li :class="{ now: step === 3 }"><span>3</span> Done</li>
    </ol>

    <section v-if="step === 0" class="admin-panel-card" aria-labelledby="setup-intro">
      <header class="admin-panel-head">
        <h2 id="setup-intro">What this does</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Agent setup">
            <p>Claude Code and Codex only use your Brain when their config on this computer points at it. This page installs that config from the vault's <code>_setup</code> folder, which a Starter export includes.</p>
            <p>It never adds a git remote and never touches credentials. Anything it replaces is backed up first.</p>
          </PanelHelp>
        </div>
      </header>
      <div class="intro">
        <p>Makes <b>Claude Code</b>, <b>Codex</b> or both on this computer use your Brain vault. You review every change before anything is written.</p>
        <dl class="will">
          <template v-for="[name, text] in WILL_DO" :key="name"><dt>{{ name }}</dt><dd>{{ text }}</dd></template>
        </dl>
        <div class="actions"><button type="button" class="primary" @click="intro = false">Continue</button></div>
      </div>
    </section>

    <section v-if="step === 1" class="admin-panel-card" aria-labelledby="setup-form">
      <header class="admin-panel-head">
        <h2 id="setup-form">1. Choose</h2>
        <div class="admin-panel-tools">
          <button type="button" class="chip" :disabled="busy || !vaultId" title="Run the vault's checks on the current setup" @click="verify">Check current setup</button>
        </div>
      </header>
      <ActionMessage v-if="!vaults.length" kind="warning" text="No vault yet. Add one on the Vaults page first." class="admin-panel-text" />
      <div v-else class="group fields">
        <div class="field">
          <FieldLabel title="Vault" for="s-vault"><p>The vault the agents will use. It becomes the active vault.</p></FieldLabel>
          <select id="s-vault" v-model="vaultId"><option v-for="v in vaults" :key="v.id" :value="v.id">{{ v.name }}</option></select>
          <p v-if="vault" class="muted path">{{ vault.path }}</p>
        </div>
        <div class="field">
          <FieldLabel title="Projects folder" for="s-root"><p>The folder that holds your code projects on this computer. It goes into the instruction text. Filled in from the vault's parent folder; change it if your code lives elsewhere.</p></FieldLabel>
          <div class="path-row">
            <input id="s-root" v-model="projectsRoot" type="text" spellcheck="false" />
            <button type="button" class="admin-icon" aria-label="Browse for a folder" title="Browse for a folder" :disabled="picking" :aria-busy="picking" @click="browse">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
            </button>
          </div>
        </div>
        <div class="field wide">
          <FieldLabel title="Set up for" bare><p>Pick the agents to configure. Both are ticked when both are installed here. Codex skill links need Windows Developer Mode.</p></FieldLabel>
          <div class="agents">
            <div class="agent">
              <ToggleSwitch v-model="claude">Claude Code</ToggleSwitch>
              <span class="status-pill" :class="{ ok: found.claude }">{{ found.claude ? "Found on this computer" : "Not found" }}</span>
            </div>
            <div class="agent">
              <ToggleSwitch v-model="codex">Codex</ToggleSwitch>
              <span class="status-pill" :class="{ ok: found.codex }">{{ found.codex ? "Found on this computer" : "Not found" }}</span>
            </div>
          </div>
        </div>
        <div class="actions">
          <button type="button" class="chip" :disabled="busy" @click="intro = true">Back</button>
          <button type="button" class="primary" :disabled="busy || !vaultId || !projectsRoot.trim() || !(claude || codex)" :aria-busy="busy" @click="plan">Review changes</button>
        </div>
      </div>
    </section>
    <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text" />

    <section v-if="step === 1 && rows.length" class="admin-panel-card" aria-labelledby="setup-verify">
      <header class="admin-panel-head"><h2 id="setup-verify">Current setup</h2></header>
      <table class="admin-records">
        <tbody>
          <tr v-for="r in rows" :key="r.name">
            <th scope="row">{{ r.name }}</th>
            <td><ActionMessage :kind="r.ok ? 'ok' : 'error'" :text="r.ok ? 'pass' : 'fail'" /></td>
            <td class="muted">{{ r.detail }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="step === 2" class="admin-panel-card" aria-labelledby="setup-plan">
      <header class="admin-panel-head">
        <h2 id="setup-plan">2. Review changes</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Review changes"><p>Each row is one change. Switch off any you do not want. Open a row to see exactly what changes. Rows marked "do by hand" cannot be done automatically.</p></PanelHelp>
          <button type="button" class="chip" :disabled="busy" @click="back">Back</button>
          <button type="button" class="primary" :disabled="busy || !on.size" :aria-busy="busy" @click="confirmOpen = true">Apply {{ on.size }} change{{ on.size === 1 ? "" : "s" }}</button>
        </div>
      </header>
      <p class="admin-panel-text muted">Nothing has been written yet. {{ changes.length }} change{{ changes.length === 1 ? "" : "s" }} ready{{ manual.length ? `, ${manual.length} to do by hand` : "" }}.</p>
      <div v-for="o in ops" :key="o.id" class="op">
        <ToggleSwitch small :checked="on.has(o.id)" :disabled="o.manual" @change="flip(o.id, ($event.target as HTMLInputElement).checked)">{{ o.label }}</ToggleSwitch>
        <span v-if="o.manual" class="status-pill">Do by hand</span>
        <details v-if="hasDiff(o)">
          <summary>{{ o.manual ? "What to do" : "Show change" }}</summary>
          <pre>{{ o.diff }}</pre>
        </details>
      </div>
    </section>

    <section v-if="step === 3" class="admin-panel-card" aria-labelledby="setup-result">
      <header class="admin-panel-head">
        <h2 id="setup-result">3. Done</h2>
        <div class="admin-panel-tools"><button type="button" class="chip" @click="back">Back to choose</button></div>
      </header>
      <table class="admin-records">
        <tbody>
          <tr v-for="r in results" :key="r.id">
            <th scope="row">{{ r.label }}</th>
            <td><ActionMessage :kind="r.status === 'error' ? 'error' : r.status === 'manual' ? 'warning' : 'ok'" :text="r.status" /></td>
            <td class="muted">{{ r.detail }}</td>
          </tr>
        </tbody>
      </table>
      <p class="admin-panel-text muted">Restart Claude Code (and Codex) so the new settings load.</p>
    </section>

    <ConfirmModal :open="confirmOpen" title="Write the setup?" :message="`${on.size} change(s) will be written to your Claude Code and Codex folders. Replaced files are backed up first.`" confirm-label="Apply" :busy="busy"
      @confirm="apply" @close="confirmOpen = false" />
  </PageLayout>
</template>

<style scoped>
.intro { display: grid; gap: 16px; padding: 20px 16px; }
.intro p { margin: 0; }
.will { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; margin: 0; }
.will dt { font-weight: 600; }
.will dd { margin: 0; color: var(--muted); }
.steps { display: flex; gap: 8px; flex-wrap: wrap; margin: 0; padding: 0; list-style: none; }
.steps li { display: flex; align-items: center; gap: 8px; padding: 4px 12px 4px 4px; border: 1px solid var(--border); border-radius: var(--radius-full); color: var(--muted); font-size: 0.9em; }
.steps li span { display: grid; place-items: center; width: 22px; height: 22px; border-radius: var(--radius-full); background: var(--surface); font-size: 0.85em; }
.steps li.now { border-color: var(--accent); color: var(--text); }
.steps li.now span { background: var(--accent); color: var(--accent-contrast); }
.steps li.done span { background: var(--success); color: var(--accent-contrast); }
.agents { display: flex; flex-wrap: wrap; gap: 12px 32px; }
.agent { display: flex; align-items: center; gap: 10px; }
.status-pill.ok { border-color: color-mix(in srgb, var(--success) 55%, var(--border)); color: var(--success); }
.group.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px 20px; padding: 20px 16px; }
.field { display: grid; gap: 4px; min-width: 0; align-content: start; }
.field.wide { grid-column: 1 / -1; }
.field > :is(input, select) { min-height: 44px; width: 100%; }
.field p { margin: 0; }
.path { font-family: var(--mono); font-size: 0.8em; overflow-wrap: anywhere; }
.path-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; }
.path-row input { min-height: 44px; }
.actions { grid-column: 1 / -1; display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.op { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; padding: 10px 16px; border-top: 1px solid var(--border); }
.op details { flex-basis: 100%; }
.op summary { cursor: pointer; color: var(--muted); font-size: 0.85em; }
.op pre { margin: 6px 0 0; max-height: 240px; overflow: auto; padding: 8px; border-radius: var(--radius-md); background: var(--code-bg); font: 0.8em var(--mono); white-space: pre-wrap; scrollbar-gutter: stable; }
.status-pill { padding: 1px 8px; border: 1px solid var(--border); border-radius: var(--radius-full); font-size: 0.8em; }
</style>
