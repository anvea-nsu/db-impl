import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import ruRU from 'antd/locale/ru_RU'
import { useAuthStore } from './store/authStore'
import AppLayout from './components/AppLayout'
import Login from './pages/Login'
import Register from './pages/Register'
import Organizations from './pages/Organizations'
import Journals from './pages/Journals'
import Authors from './pages/Authors'
import Articles from './pages/Articles'
import Statistics from './pages/Statistics'
import AdminPanel from './pages/admin/AdminPanel'

const theme = {
  token: {
    colorPrimary: '#1e2f47',
    colorLink: '#2b4a7a',
    fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
    borderRadius: 6,
    colorBgContainer: '#ffffff',
    colorBorder: '#d0dcea',
    colorBgLayout: '#f4f7fb',
  },
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { token, isAdmin } = useAuthStore()
  if (!token) return <Navigate to="/login" replace />
  if (!isAdmin()) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <ConfigProvider locale={ruRU} theme={theme}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          {/* Public routes — no auth required */}
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Navigate to="/statistics" replace />} />
            <Route path="organizations" element={<Organizations />} />
            <Route path="journals" element={<Journals />} />
            <Route path="authors" element={<Authors />} />
            <Route path="articles" element={<Articles />} />
            <Route path="statistics" element={<Statistics />} />
            <Route path="admin/*" element={<RequireAdmin><AdminPanel /></RequireAdmin>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
