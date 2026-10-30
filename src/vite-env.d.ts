/// <reference types="vite/client" />

// Tells TypeScript which environment variables the frontend reads.
// Vite only exposes variables that start with VITE_ to browser code.
interface ImportMetaEnv {
  /** Backend address, e.g. http://localhost:8000 (see .env.example) */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
