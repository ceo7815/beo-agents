import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { loadFleet } from '../api'
import type { Fleet } from '../types'

export function Home() {
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
        <h1>צי הסוכנים</h1>
        <p>
          {fleet.company} · {fleet.line}
        </p>
      </header>
      <section className="cubes" aria-label="מצב">
        <article>
          <p>סה״כ בקטלוג</p>
          <strong>{fleet.counts.total}</strong>
        </article>
        <article>
          <p>חיים</p>
          <strong className="ok">{fleet.counts.running}</strong>
        </article>
        <article>
          <p>כבויים</p>
          <strong className={fleet.counts.down ? 'down' : ''}>{fleet.counts.down}</strong>
        </article>
        <article>
          <p>מתוכננים</p>
          <strong>{fleet.counts.planned}</strong>
        </article>
      </section>
      <section className="grid">
        {fleet.agents.map((agent) => (
          <Link key={agent.id} className="card agent-card" to={`/agents/${agent.id}`}>
            <header>
              <div>
                <h3>{agent.display_name}</h3>
                <p className="role">{agent.role}</p>
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
            <p className="muted">{agent.purpose}</p>
          </Link>
        ))}
      </section>
    </div>
  )
}
