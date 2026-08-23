import { NavLink, Outlet } from 'react-router-dom'

export function Shell() {
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <strong>Beo Agents</strong>
          <span>מבינים תוכנה. מבינים AI.</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            סקירה
          </NavLink>
          <NavLink to="/agents">סוכנים</NavLink>
        </nav>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
