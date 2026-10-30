import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { RouterProvider } from './lib/router'
import { IntakeProvider } from './state/IntakeContext'
import { AuthProvider } from './state/AuthContext'
import './index.css'

// Entry point: finds <div id="root"> in index.html and renders the React app inside it.
// The providers wrap the whole app so every page can use the router, the sign-in state and the request draft.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider>
      <AuthProvider>
        <IntakeProvider>
          <App />
        </IntakeProvider>
      </AuthProvider>
    </RouterProvider>
  </StrictMode>,
)
