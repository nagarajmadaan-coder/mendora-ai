import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Vite = the tool that runs the dev server and bundles the app for production.
// The two plugins add React support and Tailwind CSS support.
export default defineConfig({
  plugins: [react(), tailwindcss()],
})
