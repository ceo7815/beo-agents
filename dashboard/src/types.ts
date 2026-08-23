export type Connection = {
  kind: string
  label: string
  connected: boolean
}

export type Agent = {
  id: string
  handle: string
  display_name: string
  role: string
  purpose: string
  status: 'live' | 'planned' | string
  folder: string
  hermes_profile: string
  channels: string[]
  platforms: string[]
  owner: string
  exists: boolean
  running: boolean
  pid: number | null
  last_log: string | null
  connections: Connection[]
}

export type Fleet = {
  company: string
  line: string
  site: string
  counts: {
    total: number
    live: number
    running: number
    down: number
    planned: number
  }
  agents: Agent[]
}

export type ActionResult = {
  ok: boolean
  error?: string
  action?: string
  agent?: string
}
