export type AppView = "normals" | "explore" | "map" | "predictions";

// The nav registry, ordered as the app reads top-to-bottom. The top group is the
// *product*: Normals (the headline, default landing) and Predictions (the next
// phase — shown disabled so the roadmap is visible, but a peer of Normals, not a
// lab tool). Explore and Map are the exploration "lab" — two presentations of the
// same explorer, kept below a divider so they read as a workbench, not headlines.
export interface ViewDef {
  id: AppView;
  label: string;
  enabled: boolean;
  group?: "lab";
}

export const VIEWS: ViewDef[] = [
  { id: "normals", label: "Normals", enabled: true },
  { id: "predictions", label: "Predictions", enabled: false },
  { id: "explore", label: "Exploration", enabled: true, group: "lab" },
  { id: "map", label: "Map", enabled: true, group: "lab" },
];
