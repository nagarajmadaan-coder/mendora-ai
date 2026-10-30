import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, api, setAuthToken, setUnauthorizedHandler, type TokenResponse, type User } from '../lib/api'

/*
  Who is signed in.

  The login token is kept in the browser's localStorage so you stay signed in after a refresh.
  (Prototype trade-off: a script injected into the page could read it. A production build
  would use secure, httpOnly cookies instead.) The token expires on the server after 60 minutes
  by default, and is removed here on sign-out or when the server rejects it.
*/

const STORAGE_KEY = 'mendora.auth'

type Status = 'loading' | 'signedOut' | 'signedIn'

interface AuthStore {
  status: Status
  user: User | null
  /** True after the server rejected the saved sign-in (e.g. it expired). Cleared on the next sign-in. */
  sessionExpired: boolean
  login: (email: string, password: string) => Promise<User>
  register: (email: string, password: string, fullName: string) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthStore | null>(null)

function readStoredToken(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return null // storage blocked (e.g. some private modes)
  }
}

function storeToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(STORAGE_KEY, token)
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore: user just won't stay signed in after a refresh */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<Status>(() => (readStoredToken() ? 'loading' : 'signedOut'))
  const [sessionExpired, setSessionExpired] = useState(false)

  const logout = useCallback(() => {
    setAuthToken(null)
    storeToken(null)
    setUser(null)
    setSessionExpired(false)
    setStatus('signedOut')
  }, [])

  // The server said our token is no longer valid (expired, or the server's secret changed).
  const expire = useCallback(() => {
    setAuthToken(null)
    storeToken(null)
    setUser(null)
    setSessionExpired(true)
    setStatus('signedOut')
  }, [])

  // On first load, check a saved token is still valid.
  useEffect(() => {
    setUnauthorizedHandler(expire)
    const token = readStoredToken()
    if (!token) return
    setAuthToken(token)
    let cancelled = false
    api
      .me()
      .then((me) => {
        if (cancelled) return
        setUser(me)
        setStatus('signedIn')
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) return // expire() already ran
        // Server unreachable: don't throw the saved sign-in away — it will be retried on the next page load.
        setAuthToken(null)
        setUser(null)
        setStatus('signedOut')
      })
    return () => {
      cancelled = true
    }
  }, [expire])

  const accept = useCallback((res: TokenResponse) => {
    setAuthToken(res.access_token)
    storeToken(res.access_token)
    setUser(res.user)
    setSessionExpired(false)
    setStatus('signedIn')
    return res.user
  }, [])

  const login = useCallback(async (email: string, password: string) => accept(await api.login({ email, password })), [accept])
  const register = useCallback(
    async (email: string, password: string, fullName: string) =>
      accept(await api.register({ email, password, full_name: fullName })),
    [accept],
  )

  const value = useMemo(
    () => ({ status, user, sessionExpired, login, register, logout }),
    [status, user, sessionExpired, login, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthStore {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
