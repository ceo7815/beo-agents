import type { ActionResult, Agent, Fleet } from './types'

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new Error(`שגיאת רשת ${res.status}`)
  }
  return (await res.json()) as T
}

export function loadFleet(): Promise<Fleet> {
  return fetch('/api/fleet').then((res) => readJson<Fleet>(res))
}

export function loadAgent(id: string): Promise<Agent> {
  return fetch(`/api/agents/${id}`).then((res) => readJson<Agent>(res))
}

export function startAgent(id: string): Promise<ActionResult> {
  return fetch(`/api/agents/${id}/start`, { method: 'POST' }).then((res) =>
    readJson<ActionResult>(res),
  )
}

export function stopAgent(id: string): Promise<ActionResult> {
  return fetch(`/api/agents/${id}/stop`, { method: 'POST' }).then((res) =>
    readJson<ActionResult>(res),
  )
}
