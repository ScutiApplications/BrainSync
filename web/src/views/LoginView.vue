<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import ActionMessage from "../components/admin/ActionMessage.vue";
import AuthCard from "../components/AuthCard.vue";
import PasswordInput from "../components/PasswordInput.vue";
import { login, session } from "../session";
import { errorMessage } from "../utils/errors";

/** Log in, or on the first run set the admin password. Only this computer (localhost) may set it. */
const router = useRouter();
const password = ref("");
const again = ref("");
const busy = ref(false);
const error = ref("");
const firstRun = computed(() => !session.configured);
const blocked = computed(() => firstRun.value && !session.canSetup);
const mismatch = computed(() => firstRun.value && again.value !== "" && again.value !== password.value);

async function submit() {
  if (busy.value || mismatch.value || blocked.value) return;
  busy.value = true;
  error.value = "";
  try {
    await login(password.value, firstRun.value);
    await router.replace("/vaults");
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AuthCard :title="firstRun ? 'Set the admin password' : 'Log in'"
    :subtitle="firstRun ? 'First run. Choose the password that protects this BrainSync.' : 'BrainSync administration.'">
    <ActionMessage v-if="blocked" kind="warning" text="No password is set yet. Open BrainSync on the computer it runs on (http://localhost:26508) to choose one. Other devices cannot." />
    <form v-else @submit.prevent="submit">
      <PasswordInput v-model="password" label="Password" :autocomplete="firstRun ? 'new-password' : 'current-password'" required autofocus />
      <PasswordInput v-if="firstRun" v-model="again" label="Repeat password" autocomplete="new-password" required />
      <ActionMessage v-if="mismatch" kind="error" text="The two passwords differ." />
      <p v-if="firstRun" class="hint">At least 8 characters.</p>
      <ActionMessage v-if="error" kind="error" :text="error" />
      <button class="primary" :disabled="busy || mismatch" :aria-busy="busy">{{ firstRun ? "Set password" : "Log in" }}</button>
    </form>
  </AuthCard>
</template>

<style scoped>
.hint { margin: 0; color: var(--muted); font-size: 0.85em; }
</style>
