/** Who is logged in. A plain reactive object: the app has one session and no store library. */
import { reactive } from "vue";
import { authApi } from "./api/brainsync";
import { onUnauthorized, setToken } from "./api/http";

export const session = reactive({ checked: false, configured: false, canSetup: false, authed: false });

export async function refreshSession(): Promise<void> {
  try {
    const s = await authApi.status();
    Object.assign(session, { configured: s.configured, canSetup: s.can_setup, authed: s.authed });
  } finally {
    session.checked = true;
  }
}

export async function login(password: string, firstRun: boolean): Promise<void> {
  const { token } = firstRun ? await authApi.setup(password) : await authApi.login(password);
  setToken(token);
  session.configured = true;
  session.canSetup = false;
  session.authed = true;
}

export async function logout(): Promise<void> {
  await authApi.logout().catch(() => {});
  setToken("");
  session.authed = false;
}

export function adoptToken(token: string): void {
  setToken(token);
}

// A 401 mid-page (expired, or the password changed on another device) sends the user back to Login.
onUnauthorized(() => {
  setToken("");
  session.authed = false;
});
