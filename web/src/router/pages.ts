/** The sidebar pages. `icon` is stroked 24x24 path data. */
export interface NavPage { to: string; label: string; icon: string[] }

export const NAV_PAGES: NavPage[] = [
  { to: "/vaults", label: "Vaults", icon: ["M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"] },
  { to: "/export", label: "Export", icon: ["M12 15V4m0 0L8 8m4-4 4 4M5 15v4h14v-4"] },
  { to: "/import", label: "Import", icon: ["M12 4v11m0 0-4-4m4 4 4-4M5 15v4h14v-4"] },
  { to: "/share", label: "Share", icon: ["M4 12a8 8 0 0 1 16 0M7.5 12a4.5 4.5 0 0 1 9 0M12 12h.01M12 12v7"] },
  { to: "/setup", label: "Agent setup", icon: ["M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.4 2.4-2.6-.6-.6-2.6z"] },
  { to: "/history", label: "History", icon: ["M12 7v5l3 2M3 12a9 9 0 1 0 3-6.7M3 4v4h4"] },
  { to: "/settings", label: "Settings", icon: ["M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6", "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1"] },
];

export function pageTitle(path: string): string {
  return NAV_PAGES.find((p) => p.to === path)?.label ?? "";
}
