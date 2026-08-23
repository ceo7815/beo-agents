import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { loadAgent, startAgent, stopAgent } from '../api'
import type { Agent } from '../types'

export function AgentDetail() {
  const { id = '' } = useParams()
  const [agent, setAgent] = useState<Agent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function refresh() {
    return loadAgent(id)
      .then(setAgent)
      .catch((err: Error) => setError(err.message))
  }

  useEffect(() => {
    void refresh()
  }, [id])

  async function run(action: 'start' | 'stop') {
    setBusy(true)
    setError(null)
    const result = action === 'start' ? await startAgent(id) : await stopAgent(id)
    if (!result.ok) setError(result.error || 'הפעולה נכשלה')
    await new Promise((resolve) => window.setTimeout(resolve, 1200))
    await refresh()
    setBusy(false)
  }

  if (!agent && !error) return <p className="muted">טוען…</p>
  if (!agent) return <p className="error">{error}</p>

  const live = agent.status === 'live'

  return (
    <div>
      <p className="muted">
        <Link to="/agents">← כל הסוכנים</Link>
      </p>
      <header className="detail-head">
        <div>
          <h2>{agent.display_name}</h2>
          <p className="muted">
            {agent.handle} · {agent.role} · {agent.owner}
          </p>
        </div>
        <span className={live ? (agent.running ? 'pill ok' : 'pill down') : 'pill wait'}>
          {!live ? 'בקרוב' : agent.running ? 'חי' : 'כבוי'}
        </span>
      </header>
      <p>{agent.purpose}</p>
      {error ? <p className="error">{error}</p> : null}
      <div className="actions">
        <button className="btn" disabled={!live || busy || agent.running} onClick={() => void run('start')}>
          הפעל gateway
        </button>
        <button
          className="btn ghost"
          disabled={!live || busy || !agent.running}
          onClick={() => void run('stop')}
        >
          כבה
        </button>
      </div>
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
      {agent.last_log ? <pre className="log">{agent.last_log}</pre> : null}
    </div>
  )
}
