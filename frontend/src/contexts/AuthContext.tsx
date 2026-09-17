import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { api } from '../services/api'
import type { User } from '../types/api'

interface AuthContextValue {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  login: (userId: string, apiKey: string) => Promise<void>
  logout: () => void
  isLoading: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    try {
      const stored = sessionStorage.getItem('sentinel_user')
      return stored ? JSON.parse(stored) : null
    } catch { return null }
  })
  const [token, setToken] = useState<string | null>(() =>
    sessionStorage.getItem('sentinel_token')
  )
  const [isLoading, setIsLoading] = useState(false)

  const login = useCallback(async (userId: string, apiKey: string) => {
    setIsLoading(true)
    try {
      const session = await api.createSession({ user_id: userId, api_key: apiKey })
      setUser(session.user)
      setToken(session.token)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    api.clearToken()
    setUser(null)
    setToken(null)
  }, [])

  return (
    <AuthContext.Provider value={{
      user,
      token,
      isAuthenticated: !!token && !!user,
      login,
      logout,
      isLoading,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
