<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from "vue";
import { shareApi, vaultApi, type ShareStatus, type Vault } from "../api/brainsync";
import ActionMessage from "../components/admin/ActionMessage.vue";
import FieldLabel from "../components/admin/FieldLabel.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import RecordDrawer from "../components/admin/RecordDrawer.vue";
import PageLayout from "../components/PageLayout.vue";
import ToggleSwitch from "../components/ToggleSwitch.vue";
import { errorMessage } from "../utils/errors";
import "../components/admin/admin.css";

/** Turn sharing on for chosen vaults. Off at every start. The switch stays pending until the server answers. */
interface Pick { on: boolean; paths: string; privatePaths: string }
const vaults = ref<Vault[]>([]);
const status = ref<ShareStatus>({ active: false, code: "", peers: [] });
const picks = reactive<Record<string, Pick>>({});
const setupOpen = ref(false);
const pending = ref(false);
const error = ref("");
let timer: number | undefined;

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

async function refresh() {
  try {
    status.value = await shareApi.status();
  } catch (err) {
    error.value = errorMessage(err);
  }
}

onMounted(async () => {
  try {
    vaults.value = await vaultApi.list();
    for (const v of vaults.value) picks[v.id] = { on: false, paths: "", privatePaths: "" };
  } catch (err) {
    error.value = errorMessage(err);
  }
  await refresh();
  timer = window.setInterval(refresh, 3000); // new devices show up within seconds
});
onUnmounted(() => window.clearInterval(timer));

async function start() {
  const selections: Record<string, { filter: { paths: string[] }; include_private: string[] }> = {};
  for (const v of vaults.value) {
    const p = picks[v.id];
    if (p?.on) selections[v.id] = { filter: { paths: csv(p.paths) }, include_private: lines(p.privatePaths) };
  }
  if (!Object.keys(selections).length) { error.value = "Switch on at least one vault."; return; }
  pending.value = true;
  error.value = "";
  try {
    await shareApi.start(selections);
    setupOpen.value = false;
    await refresh();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    pending.value = false;
  }
}

async function stop() {
  pending.value = true;
  error.value = "";
  try {
    await shareApi.stop();
    await refresh();
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    pending.value = false;
  }
}

async function revoke(id: string) {
  try {
    await shareApi.revoke(id);
    await refresh();
  } catch (err) {
    error.value = errorMessage(err);
  }
}
</script>

<template>
  <PageLayout class="admin-panel" title="Share" wide>
    <section class="admin-panel-card" aria-labelledby="share-state">
      <header class="admin-panel-head">
        <h2 id="share-state">Live share</h2>
        <div class="admin-panel-tools">
          <PanelHelp title="Live share">
            <p>While sharing is on, another BrainSync on this network can connect with the pairing code, browse what you chose and pull it. They can read only; they cannot change anything here.</p>
            <p><b>On:</b> devices on your network can pair. <b>Off:</b> nothing is reachable and every paired device is dropped. Sharing is off every time BrainSync starts.</p>
          </PanelHelp>
          <ToggleSwitch :checked="status.active" :disabled="pending" :aria-busy="pending"
            @click.prevent="status.active ? stop() : (setupOpen = true)">{{ status.active ? "Sharing" : "Not sharing" }}</ToggleSwitch>
        </div>
      </header>
      <ActionMessage v-if="error" kind="error" :text="error" class="admin-panel-text" />
      <div v-if="status.active" class="live">
        <p class="admin-panel-text">Pairing code <strong class="code">{{ status.code }}</strong></p>
        <p class="admin-panel-text muted">On the other device open Import, enter this computer's network address with port 26508 and this code.</p>
        <p v-if="!status.peers.length" class="admin-panel-text muted">No device has paired yet.</p>
        <div v-else class="admin-table-scroll" tabindex="0" role="region" aria-label="Paired devices">
          <table class="admin-records">
            <thead><tr><th scope="col">Device</th><th scope="col">Address</th><th scope="col">Since</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
            <tbody>
              <tr v-for="p in status.peers" :key="p.device_id">
                <th scope="row">{{ p.name }}</th><td>{{ p.ip }}</td><td>{{ p.since }}</td>
                <td><button type="button" class="chip" @click="revoke(p.device_id)">Revoke</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <p v-else class="admin-panel-text muted">Switch sharing on to choose what other devices may pull.</p>
    </section>

    <RecordDrawer :open="setupOpen" title="Start sharing" :editing="false" :busy="pending" @close="setupOpen = false">
      <form id="share-start" class="admin-editor" @submit.prevent="start">
        <p v-if="!vaults.length" class="muted">Add a vault first.</p>
        <section v-for="v in vaults" :key="v.id" class="share-vault">
          <ToggleSwitch :checked="picks[v.id]!.on" @change="picks[v.id]!.on = ($event.target as HTMLInputElement).checked" :disabled="pending">{{ v.name }}</ToggleSwitch>
          <template v-if="picks[v.id]?.on">
            <FieldLabel title="Paths to share" :for="`sp-${v.id}`"><p>Globs separated by commas, for example <code>Notes/*, Projects/*</code>. Empty shares every note that is not private.</p></FieldLabel>
            <input :id="`sp-${v.id}`" v-model="picks[v.id]!.paths" type="text" spellcheck="false" :disabled="pending" />
            <FieldLabel title="Private notes to share" :for="`pp-${v.id}`"><p>Private notes are never shared by a filter. Write the exact path of each one you want to share, one per line.</p></FieldLabel>
            <textarea :id="`pp-${v.id}`" v-model="picks[v.id]!.privatePaths" rows="3" spellcheck="false" :disabled="pending"></textarea>
          </template>
        </section>
      </form>
      <template #footer>
        <button type="submit" form="share-start" class="primary" :disabled="pending" :aria-busy="pending">Start sharing</button>
      </template>
    </RecordDrawer>
  </PageLayout>
</template>

<style scoped>
.live { display: grid; }
.code { font: 600 1.4em var(--mono); letter-spacing: 0.15em; color: var(--accent); }
.share-vault { display: grid; gap: 8px; padding-block: 12px; border-top: 1px solid var(--border); }
</style>
