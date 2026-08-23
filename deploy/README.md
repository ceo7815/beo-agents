# xCloud — Deploy via Git (same flow as Beo OS / Titatu)

On `beo-systems-1` → **+ New Site** → **Deploy Any App From Git**:

1. Click **Private Repository** (not Public).
2. Select **`ceo7815/beo-agents`** — never `ceo-digital/*`, never `titatu-agents`.
3. Branch: `main`
4. Deploy with **docker-compose.yml**
5. Docker Compose file: `docker-compose.yml`
6. Port: **8788**
7. Site name: `Beo-agents`
8. Domain when ready: `agents.beosystem.com` (or xCloud preview until DNS)

Enable push-to-deploy (webhook).

## Environment (xCloud → Environment)

| Key | Value |
| --- | --- |
| `OPENAI_API_KEY` | same Beo key |
| `OPENAI_MODEL` | `gpt-5.6-luna` |
| `TELEGRAM_BOT_TOKEN` | שי / Beo Leads bot |
| `SOCIAL_TELEGRAM_BOT_TOKEN` | עדי / Beo Social bot |
| `TELEGRAM_ALLOWED_USERS` | Or's Telegram id |
| `GMAIL_FROM` | `sales@beosystem.com` |
| `GMAIL_FROM_NAME` | `שי \| Beo Systems` |
| `WHATSAPP_ME_URL` | `https://wa.me/33632519053` |

Then Deploy. Beo OS should proxy `/api/beo-agents` to `http://127.0.0.1:8788`.

The control container mounts Docker (`/var/run/docker.sock`) so Beo OS can start/stop עדי (`beo-social`) without a Hermes gateway button. שי is on/off inside control (Telegram poller), not a separate gateway.
