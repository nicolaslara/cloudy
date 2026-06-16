/// <reference types="vite/client" />

// Declare the one custom build-time env var we read so `import.meta.env.VITE_API_URL`
// is typed as `string | undefined` (it is absent in dev) rather than `any`. See
// src/api/client.ts for how it selects the backend host.
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
