# Beo-agents



Hermes agents for **Beo Systems**. One folder per agent. Telegram gateway on our side. Not Nous cloud.



GitHub: `github.com/ceo7815/beo-agents` only. Do not push to ceo-digital or Hub. Do not mix with Titatu / Mochka.



## Fleet dashboard



Local control of every company agent. Catalog is the source of truth.



1. `.\scripts\run-dashboard.ps1`

2. Open [http://127.0.0.1:5174](http://127.0.0.1:5174)



The UI talks to `http://127.0.0.1:8788` (control API). Start / stop runs `hermes -p <profile> gateway`. Secrets never leave the agent `.env`.



## v1 — Beo Social (`social.beo`)



Company content agent (אור). Instagram + Facebook copy and images. Talks on **Telegram**. No auto-publish to Meta yet (the dashboard shows that honestly).



```powershell

.\scripts\run-social-beo.ps1

```



Or start it from the dashboard agent page.



## v1 — Beo Leads (`leads.beo` / שי)

Israeli outreach. Public emails from the company site only. Drafts wait in **Beo OS** (`/ai-agents/leads-beo`). No follow-up. Telegram bot later.

```powershell
.\scripts\run-control.ps1
.\scripts\run-leads-daily.ps1
.\scripts\link-leads-beo-profile.ps1
```

Copy `agents/leads-beo/.env.example` → `.env`. Gmail API and the dedicated mailbox come later.

## Add the next agent



1. New folder under `agents/` (copy the idea of `social-beo`, not its `.env`).

2. New Telegram bot. New Hermes profile. New compose service later.

3. Add a row to `catalog/agents.json`.

4. It appears on the dashboard.



## Layout



```

Beo-agents/

  catalog/agents.json    ← fleet registry

  control/               ← local status + start/stop API

  dashboard/             ← Beo Agents UI

  agents/social-beo/     ← Hermes home for Beo Social
  agents/leads-beo/      ← שי / Beo Leads (pipeline + drafts)

  docker-compose.yml     ← server, after local works

```

