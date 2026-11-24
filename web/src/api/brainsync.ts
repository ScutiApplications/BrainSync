/** Typed calls to the BrainSync API. */
import { apiRequest } from "./http";

export interface Vault { id: string; name: string; path: string; private_folders: string[]; active: boolean }
export interface Item { path: string; sha256: string; size: number; mtime: number; type: string; status: string; tags: string[]; created: string; private: boolean }
export interface Filter {
  paths: string[]; types: string[]; statuses: string[]; tags: string[];
  created_from: string; created_to: string; modified_from: string; modified_to: string; changed_since_peer: string;
}
export interface SelectionBody { filter?: Partial<Filter>; include?: string[]; include_private?: string[]; exclude?: string[]; use_filter?: boolean }
export interface Hunk { kind: "clean" | "conflict"; lines?: string[]; mine?: string[]; theirs?: string[] }
export interface PreviewRow { path: string; state: string; private: boolean; binary: boolean; default: string; hunks?: Hunk[]; conflicts?: number }
export interface Preview { pack_id: string; source_device_id: string; vault_name: string; rows: PreviewRow[] }
export interface Decision { action: string; choices?: Record<string, string> }
export interface ApplyResult { applied: string[]; skipped: string[]; backup: string | null }
export interface SharePeer { device_id: string; name: string; ip: string; since: string }
export interface ShareStatus { active: boolean; code: string; peers: SharePeer[] }
export interface SetupOp { id: number; label: string; diff: string; manual: boolean }
export interface SetupResult { id: number; label: string; status: string; detail: string }
export interface VerifyRow { name: string; ok: boolean; detail: string }
export interface SettingOption { key: string; label: string; help: string; kind: "int" | "str"; default: string | number; restart: boolean; min: number | null; max: number | null; value: string | number; changed: boolean }
export interface AuthStatus { configured: boolean; can_setup: boolean; authed: boolean }
export interface AuditEntry { ts: string; event: string; [key: string]: unknown }

const get = <T>(path: string) => apiRequest<T>("GET", path);
const post = <T>(path: string, body?: unknown) => apiRequest<T>("POST", path, body);

export const authApi = {
  status: () => get<AuthStatus>("api/auth/status"),
  setup: (password: string) => post<{ token: string }>("api/auth/setup", { password }),
  login: (password: string) => post<{ token: string }>("api/auth/login", { password }),
  logout: () => post<{ ok: boolean }>("api/auth/logout"),
  changePassword: (current: string, next: string) => post<{ token: string }>("api/auth/password", { current, new: next }),
};

export interface DirListing { path: string; parent: string | null; dirs: string[]; is_vault: boolean }

export const fsApi = {
  dirs: (path: string) => get<DirListing>(`api/fs/dirs?path=${encodeURIComponent(path)}`),
};

export const vaultApi = {
  list: async () => (await get<{ vaults: Vault[] }>("api/vaults")).vaults,
  add: (name: string, path: string, create: boolean) => post<Vault>("api/vaults", { name, path, create }),
  remove: (id: string) => apiRequest<{ ok: boolean }>("DELETE", `api/vaults/${id}`),
  setPrivateFolders: (id: string, folders: string[]) => apiRequest<{ ok: boolean }>("PUT", `api/vaults/${id}/private-folders`, { folders }),
  setActive: (id: string) => post<{ ok: boolean }>(`api/vaults/${id}/active`),
  select: (id: string, selection: SelectionBody) => post<{ all: Item[]; selected: string[] }>(`api/vaults/${id}/select`, { selection }),
  exportPack: (id: string, selection: SelectionBody) => apiRequest<Blob>("POST", `api/vaults/${id}/export`, { selection }, { blob: true }),
};

export const importApi = {
  upload: (vaultId: string, file: Blob) => apiRequest<Preview>("POST", `api/import/upload?vault_id=${vaultId}`, undefined, { raw: file }),
  apply: (vaultId: string, packId: string, decisions: Record<string, Decision>) =>
    post<ApplyResult>("api/import/apply", { vault_id: vaultId, pack_id: packId, decisions }),
};

export const shareApi = {
  status: () => get<ShareStatus>("api/share/status"),
  start: (selections: Record<string, SelectionBody>) => post<{ code: string }>("api/share/start", { selections }),
  stop: () => post<{ ok: boolean }>("api/share/stop"),
  revoke: (deviceId: string) => apiRequest<{ ok: boolean }>("DELETE", `api/share/peers/${deviceId}`),
};

export const peerApi = {
  connect: (address: string, code: string) => post<{ cid: string; name: string }>("api/peer/connect", { address, code }),
  vaults: async (cid: string) => (await get<{ vaults: { id: string; name: string }[] }>(`api/peer/${cid}/vaults`)).vaults,
  manifest: (cid: string, vid: string) => get<{ vault_name: string; items: Item[] }>(`api/peer/${cid}/vaults/${vid}/manifest`),
  pull: (cid: string, vid: string, paths: string[], vaultId: string) => post<Preview>(`api/peer/${cid}/vaults/${vid}/pull`, { paths, vault_id: vaultId }),
  close: (cid: string) => apiRequest<{ ok: boolean }>("DELETE", `api/peer/${cid}`),
};

export interface SetupBody { vault_id: string; projects_root: string; codex: boolean; selected: number[] }
export const setupApi = {
  plan: async (b: SetupBody) => (await post<{ ops: SetupOp[] }>("api/setup/plan", b)).ops,
  apply: async (b: SetupBody) => (await post<{ results: SetupResult[] }>("api/setup/apply", b)).results,
  verify: async (b: SetupBody) => (await post<{ rows: VerifyRow[] }>("api/setup/verify", b)).rows,
};

export const settingsApi = {
  list: async () => (await get<{ options: SettingOption[] }>("api/settings")).options,
  set: async (key: string, value: string | number) => (await apiRequest<{ options: SettingOption[] }>("PUT", `api/settings/${key}`, { value })).options,
  reset: async (key: string) => (await apiRequest<{ options: SettingOption[] }>("DELETE", `api/settings/${key}`)).options,
};

export const historyApi = {
  get: () => get<{ audit: AuditEntry[]; backups: string[] }>("api/history"),
};
