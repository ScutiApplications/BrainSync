<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { authApi, settingsApi, type SettingOption } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import FieldLabel from "../components/admin/FieldLabel.vue";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import PasswordInput from "../components/PasswordInput.vue";
import { adoptToken } from "../session";
import { errorMessage } from "../utils/errors";

/** Every setting lives in the database and a saved change applies at once. Only Listen address and Port wait for a restart. */
const options = ref<SettingOption[]>([]);
const draft = ref<Record<string, string>>({});
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const search = ref("");
const panel = ref<InstanceType<typeof SettingsPanel>>();

const current = ref("");
const next = ref("");
const again = ref("");
const passwordBusy = ref(false);
const passwordMessage = ref<{ kind: "ok" | "error"; text: string } | null>(null);

function apply(list: SettingOption[]) {
  options.value = list;
  draft.value = Object.fromEntries(list.map((o) => [o.key, String(o.value)]));
}

onMounted(async () => {
  try {
    apply(await settingsApi.list());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

const changed = computed(() => options.value.filter((o) => draft.value[o.key] !== String(o.value)));
const dirty = computed(() => changed.value.length > 0);
const restartNeeded = computed(() => changed.value.some((o) => o.restart));
const shown = (o: SettingOption) => panel.value?.matches(o.label, o.help) ?? true;

function parsed(o: SettingOption): string | number {
  return o.kind === "int" ? Number(draft.value[o.key]) : draft.value[o.key]!;
}

async function save() {
  if (!dirty.value || saving.value) return;
  saving.value = true;
  error.value = notice.value = "";
  try {
    let list = options.value;
    const restart = restartNeeded.value;
    for (const o of changed.value) list = await settingsApi.set(o.key, parsed(o));
    apply(list);
    notice.value = restart ? "Saved. Listen address and Port apply at the next start; everything else applies now." : "Saved. Applied now.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

async function reset(o: SettingOption) {
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await settingsApi.reset(o.key));
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

const passwordMismatch = computed(() => again.value !== "" && again.value !== next.value);

async function changePassword() {
  if (passwordBusy.value || passwordMismatch.value) return;
  passwordBusy.value = true;
  passwordMessage.value = null;
  try {
    adoptToken((await authApi.changePassword(current.value, next.value)).token);
    current.value = next.value = again.value = "";
    passwordMessage.value = { kind: "ok", text: "Password changed. Other devices must log in again." };
  } catch (err) {
    passwordMessage.value = { kind: "error", text: errorMessage(err) };
  } finally {
    passwordBusy.value = false;
  }
}
</script>

<template>
  <SettingsPanel ref="panel" v-model:search="search" title="Settings" heading="Server settings" label="settings" :dirty="dirty" :saving="saving" @save="save" @discard="apply(options)">
    <template #help>
      <p>How this BrainSync behaves. All of it is stored in the database, not in a file, and a saved change applies at once.</p>
      <p>Only <b>Listen address</b> and <b>Port</b> need a restart. A setting that differs from its default shows a Reset button.</p>
    </template>
    <p v-if="loading" class="note muted" role="status">Loading settings…</p>
    <ActionMessage v-if="error" kind="error" :text="error" class="note" />
    <ActionMessage v-else-if="notice" kind="ok" :text="notice" class="note" />
    <div v-if="!loading" class="group">
      <h3>Behaviour</h3>
      <p class="help">Saved in the database. Press Save in the header to apply.</p>
      <div v-for="o in options" v-show="shown(o)" :key="o.key" class="field">
        <FieldLabel :title="o.label" :for="`opt-${o.key}`">
          <p>{{ o.help }}</p>
          <p v-if="o.min !== null">Allowed: {{ o.min }} to {{ o.max }}. Default: {{ o.default === "" ? "computer name" : o.default }}.</p>
          <p v-else>Default: {{ o.default === "" ? "computer name" : o.default }}.</p>
        </FieldLabel>
        <input :id="`opt-${o.key}`" v-model="draft[o.key]" :type="o.kind === 'int' ? 'number' : 'text'" :min="o.min ?? undefined" :max="o.max ?? undefined" spellcheck="false" :disabled="saving" />
        <span v-if="o.restart" class="muted small">Applies at the next start.</span>
        <button v-if="o.changed" type="button" class="link-btn" :disabled="saving" @click="reset(o)">Reset to default</button>
      </div>
    </div>
    <form v-if="!loading" class="group" @submit.prevent="changePassword">
      <h3>Admin password</h3>
      <p class="help">Changing it logs every other device out.</p>
      <PasswordInput v-model="current" label="Current password" autocomplete="current-password" required :disabled="passwordBusy" />
      <PasswordInput v-model="next" label="New password (8 or more characters)" autocomplete="new-password" required :disabled="passwordBusy" />
      <PasswordInput v-model="again" label="Repeat new password" autocomplete="new-password" required :disabled="passwordBusy" />
      <ActionMessage v-if="passwordMismatch" kind="error" text="The two new passwords differ." />
      <ActionMessage v-if="passwordMessage" :kind="passwordMessage.kind" :text="passwordMessage.text" />
      <div class="actions"><button class="primary" :disabled="passwordBusy || passwordMismatch" :aria-busy="passwordBusy">Change password</button></div>
    </form>
  </SettingsPanel>
</template>

<style scoped>
.note { margin: 0; padding: 12px 16px 0; }
.muted { color: var(--muted); }
.small { font-size: 0.8em; }
.group { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px 20px; align-content: start; padding: 20px 16px; }
.group > h3, .group > .help, .group > .actions, .group > :is(p, .action-message) { grid-column: 1 / -1; }
.group > h3 { padding-bottom: 8px; border-bottom: 1px solid var(--border); margin: 0; font-size: 1em; }
.group + .group { border-top: 1px solid var(--border); }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.field { display: grid; gap: 4px; min-width: 0; align-content: start; }
.field > input { min-width: 0; min-height: 44px; width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); }
.field > input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.actions { display: flex; justify-content: flex-end; }
</style>
