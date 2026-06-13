export type AppView = "explore" | "map" | "averages" | "predictions";

export const VIEWS: { id: AppView; label: string; enabled: boolean }[] = [
  { id: "explore", label: "Explore", enabled: true },
  { id: "map", label: "Map", enabled: true },
  { id: "averages", label: "Averages", enabled: false },
  { id: "predictions", label: "Predictions", enabled: false },
];
