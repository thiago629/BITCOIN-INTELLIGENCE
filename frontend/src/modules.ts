// Single source of truth for the platform's modules and their delivery phase.
// Modules without `path` are not built yet: the sidebar shows them disabled
// with their phase instead of linking to an empty page.

export interface ModuleDef {
  key: string;
  label: string;
  path?: string;
  phase: number;
  icon: string; // SVG path data (24x24 viewBox)
}

export const MODULES: ModuleDef[] = [
  { key: "dashboard", label: "Dashboard", path: "/", phase: 1, icon: "M3 13h8V3H3zm0 8h8v-6H3zm10 0h8V11h-8zm0-18v6h8V3z" },
  { key: "explorer", label: "Blockchain Explorer", path: "/explorer", phase: 1, icon: "M4 6h16M4 12h16M4 18h10" },
  { key: "whales", label: "Whale Tracker", path: "/whales", phase: 2, icon: "M3 12c3-6 15-6 18 0-3 6-15 6-18 0z" },
  { key: "data", label: "Data Intelligence", phase: 2, icon: "M4 20V10m6 10V4m6 16v-7m4 7H2" },
  { key: "alerts", label: "Alerts", path: "/alerts", phase: 2, icon: "M12 3a6 6 0 016 6v4l2 3H4l2-3V9a6 6 0 016-6zm-2 16h4" },
  { key: "network", label: "Network Intelligence", phase: 3, icon: "M5 6a2 2 0 104 0 2 2 0 00-4 0m10 12a2 2 0 104 0 2 2 0 00-4 0M7 8l10 8" },
  { key: "anomaly", label: "Anomaly Detection", phase: 3, icon: "M3 12h4l3-8 4 16 3-8h4" },
  { key: "reports", label: "AI Reports", phase: 4, icon: "M6 3h9l4 4v14H6zM9 12h7M9 16h7" },
  { key: "system", label: "Estado del sistema", path: "/system", phase: 1, icon: "M12 8a4 4 0 100 8 4 4 0 000-8zm0-5v3m0 12v3M3 12h3m12 0h3" },
];
