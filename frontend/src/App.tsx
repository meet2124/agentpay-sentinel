import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Sidebar from './components/Sidebar'
import LoginPage from './pages/LoginPage'
import OverviewPage from './pages/OverviewPage'
import EvaluatePage from './pages/EvaluatePage'
import EvidencePage from './pages/EvidencePage'
import AuditPage from './pages/AuditPage'
import PolicyPage from './pages/PolicyPage'

function AppRoutes() {
  const { isAuthenticated } = useAuth()

  if (!isAuthenticated) {
    return <LoginPage />
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content">
        <Routes>
          <Route path="/"         element={<OverviewPage />} />
          <Route path="/evaluate" element={<EvaluatePage />} />
          <Route path="/evidence" element={<EvidencePage />} />
          <Route path="/audit"    element={<AuditPage />} />
          <Route path="/policy"   element={<PolicyPage />} />
          <Route path="*"         element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
