export type AppView =
  | "normals"
  | "predictions"
  | "damped_persistence"
  | "explore"
  | "map";

// The nav registry, ordered top-to-bottom and split into labelled groups. The
// top (ungrouped) entries are the product surface — Normals and the live
// Predictions outlook. "models" holds one tab per prediction model (named after
// the model; more arrive as we add them). "lab" is the exploration workbench,
// kept under its own divider so it reads as secondary, not a headline.
export type ViewGroup = "models" | "lab";

export const GROUP_LABELS: Record<ViewGroup, string> = {
  models: "Models",
  lab: "Lab",
};

export interface ViewDef {
  id: AppView;
  label: string;
  enabled: boolean;
  group?: ViewGroup;
}

export const VIEWS: ViewDef[] = [
  { id: "normals", label: "Normals", enabled: true },
  { id: "predictions", label: "Predictions", enabled: true },
  { id: "damped_persistence", label: "Damped persistence", enabled: true, group: "models" },
  { id: "explore", label: "Exploration", enabled: true, group: "lab" },
  { id: "map", label: "Map", enabled: true, group: "lab" },
];
