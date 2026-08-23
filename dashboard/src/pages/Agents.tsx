import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { loadFleet } from '../api'
import type { Fleet } from '../types'

export function Agents() {
  const [fleet, setFleet] = useState<Fleet | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadFleet()
      .then(setFleet)
      .catch((err: Error) => setError(err.message))
  }, [])

  if (error) return <p className="error">{error}</p>
  if (!fleet) return <p className="muted">טוען…</p>

  return (
    <div>
      <header className="page-head">
        <h2>סוכנים</h2>
        <p>תיקייה אחת = סוכן אחד. הקטלוג הוא מקור האמת.</p>
      </header>
      <section className="grid">
        {fleet.agents.map((agent) => (
          <Link key={agent.id} className="card agent-card" to={`/agents/${agent.id}`}>
            <header>
              <div>
                <h3>{agent.display_name}</h3>
                <p className="role">
                  {agent.handle} · {agent.role}
                </p>
              </div>
              <span
                className={
                  agent.status !== 'live'
                    ? 'pill wait'
                    : agent.running
                      ? 'pill ok'
                      : 'pill down'
                }
              >
                {agent.status !== 'live' ? 'בקרוב' : agent.running ? 'חי' : 'כבוי'}
              </span>
            </header>
            <ul className="conns">
              {agent.connections.map((conn) => (
                <li key={conn.kind}>
                  <span>{conn.label}</span>
                  <em className={conn.connected ? 'ok' : 'down'}>
                    {conn.connected ? 'מחובר' : 'לא מחובר'}
                  </em>
                </li>
              ))}
            </ul>
          </Link>
        ))}
        <article className="card add-card">
          <h3>סוכן הבא</h3>
          <p className="muted">
            מוסיפים שורה ב־<code>catalog/agents.json</code>, תיקייה חדשה תחת{' '}
            <code>agents/</code>, בוט טלגרם חדש, ופרופיל Hermes נפרד. בלי לשתף טוקנים.
          </p>
        </article>
      </section>
    </div>
  )
}
