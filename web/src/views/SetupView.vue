<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { setupApi, vaultApi, type SetupBody, type SetupOp, type SetupResult, type VerifyRow, type Vault } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import FieldLabel from "../components/admin/FieldLabel.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import PageLayout from "../components/PageLayout.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** Install the Claude Code and Codex config from the vault's _setup folder. Plan first; nothing is written until Apply. */
const vaults = ref<Vault[]>([]);
const vaultId = ref("");
const projectsRoot = ref("");
const codex = ref(false);
const ops = ref<SetupOp[]>([]);
const on = ref(new Set<number>());
const results = ref<SetupResult[]>([]);
const rows = ref<VerifyRow[]>([]);
const busy = ref(false);
const error = ref("");
const confirmOpen = ref(false);

const body = computed<SetupBody>(() => ({ vault_id: vaultId.value, projects_root: projectsRoot.value, codex: codex.value, selected: [...on.value] }));

onMounted(async () => {
  try {
    vaults.value = await vaultApi.list();
    vaultId.value = vaults.value.find((v) => v.active)?.id ?? vaults.value[0]?.id ?? "";
  } catch (err) {
    error.value = errorMessage(err);
  }
});

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

function flip(id: number, checked: boolean) {
  if (checked) on.value.add(id);
  else on.value.delete(id);
}
</script>

<template>
  <PageLayout class="admin-panel" title="Agent setup" wide>
    <section class="admin-panel-card" aria-labelledby="setup-form">
      <header class="admin-panel-head">
        <h2 id="setup-form">Claude Code and Codex</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Agent setup">
            <p>Installs the hooks, skills, settings and instruction text from the vault's <code>_setup</code> folder so Claude Code (and Codex) can use this vault. The vault becomes the active one.</p>
            <p>Plan shows every file it would write, with a diff. Apply writes only what is switched on, and keeps a backup of anything it replaces. It never adds a git remote and never touches credentials.</p>
          </PanelHelp>
        </div>
      </header>
      <div class="group fields">
        <div class="field">
          <FieldLabel title="Vault" for="s-vault"><p>The vault to set up. It needs a <code>_setup</code> folder, which a Starter export includes.</p></FieldLabel>
          <select id="s-vault" v-model="vaultId"><option v-for="v in vaults" :key="v.id" :value="v.id">{{ v.name }}</option></select>
        </div>
        <div class="field">
          <FieldLabel title="Projects folder" for="s-root"><p>The folder that holds your code projects on this computer. It goes into the instruction text, for example <code>D:\Code</code>.</p></FieldLabel>
          <input id="s-root" v-model="projectsRoot" type="text" spellcheck="false" />
        </div>
        <div class="field">
          <FieldLabel title="Codex" bare><p><b>On:</b> also set up Codex (instructions, skill links, writable folders). Skill links need Windows Developer Mode. <b>Off:</b> Claude Code only.</p></FieldLabel>
          <ToggleSwitch v-model="codex">Also set up Codex</ToggleSwitch>
        </div>
        <div class="actions">
          <button type="button" class="chip" :disabled="busy || !vaultId" @click="verify">Verify</button>
          <button type="button" class="primary" :disabled="busy || !vaultId || !projectsRoot.trim()" :aria-busy="busy" @click="plan">Plan</button>
        </div>
      </div>
    </section>
    <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text" />

    <section v-if="ops.length" class="admin-panel-card" aria-labelledby="setup-plan">
      <header class="admin-panel-head">
        <h2 id="setup-plan">Plan</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Plan"><p>Switch off any change you do not want. Rows that need manual work are off and tell you what to do.</p></PanelHelp>
          <button type="button" class="primary" :disabled="busy || !on.size" :aria-busy="busy" @click="confirmOpen = true">Apply {{ on.size }}</button>
        </div>
      </header>
      <div v-for="o in ops" :key="o.id" class="op">
        <ToggleSwitch small :checked="on.has(o.id)" :disabled="o.manual" @change="flip(o.id, ($event.target as HTMLInputElement).checked)">{{ o.label }}</ToggleSwitch>
        <pre>{{ o.diff }}</pre>
      </div>
    </section>

    <section v-if="results.length" class="admin-panel-card" aria-labelledby="setup-result">
      <header class="admin-panel-head"><h2 id="setup-result">Result</h2></header>
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

    <section v-if="rows.length" class="admin-panel-card" aria-labelledby="setup-verify">
      <header class="admin-panel-head"><h2 id="setup-verify">Checks</h2></header>
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

    <ConfirmModal :open="confirmOpen" title="Write the setup?" :message="`${on.size} change(s) will be written to your Claude Code and Codex folders. Replaced files are backed up first.`" confirm-label="Apply" :busy="busy"
      @confirm="apply" @close="confirmOpen = false" />
  </PageLayout>
</template>

<style scoped>
.group.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px 20px; padding: 20px 16px; }
.field { display: grid; gap: 4px; min-width: 0; align-content: start; }
.field > :is(input, select) { min-height: 44px; width: 100%; }
.actions { grid-column: 1 / -1; display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; }
.op { display: grid; gap: 4px; padding: 10px 16px; border-top: 1px solid var(--border); }
.op pre { margin: 0; max-height: 240px; overflow: auto; padding: 8px; border-radius: var(--radius-md); background: var(--code-bg); font: 0.8em var(--mono); white-space: pre-wrap; scrollbar-gutter: stable; }
</style>
