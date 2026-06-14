import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import "./index.css";

// Entry point: mount React under a single QueryClient so every hook shares one
// cache and dedupes in-flight requests. Defaults are intentionally library-stock
// here — per-query staleTime/cache tuning lives at each useQuery call site.
const queryClient = new QueryClient();

// Fail loudly if the host HTML is missing #root — a silent no-render is far
// harder to diagnose than this throw.
const root = document.getElementById("root");
if (!root) throw new Error("missing #root element");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
