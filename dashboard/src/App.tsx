import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AgentDetail } from './pages/AgentDetail'
import { Agents } from './pages/Agents'
import { Home } from './pages/Home'
import { Shell } from './pages/Shell'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route path="/" element={<Home />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/agents/:id" element={<AgentDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
