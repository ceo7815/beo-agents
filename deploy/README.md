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
| `JOHNNY_TELEGRAM_BOT_TOKEN` | ג׳וני — בוט **נפרד**, לא של שי |
| `TELEGRAM_ALLOWED_USERS` | Or's Telegram id |
| `BOT_API_KEY` | same key as Beo OS Node `BOT_API_KEY` |
| `JOHNNY_ACTOR_USER_ID` | Firestore uid of אור in Beo OS |
| `BEO_OS_URL` | `https://os.beosystem.com` |
| `GMAIL_FROM` | `sales@beosystem.com` |
| `GMAIL_FROM_NAME` | `Shay_Beo_Systems` |
| `GMAIL_REFRESH_TOKEN` | Shay `sales@` (connect once on the PC) |
| `GMAIL_CLIENT_ID` | Google OAuth client id |
| `GMAIL_CLIENT_SECRET` | Google OAuth client secret |
| `CEO_GMAIL_REFRESH_TOKEN` | ג׳וני `ceo@beosystem.co.il` + Calendar + Meet |
| `GOOGLE_CALENDAR_ID` | `primary` unless a dedicated calendar |
| `RIVHIT_API_KEY` | ריווחית אונליין — later, leave empty until you have it |
| `WHATSAPP_ME_URL` | `https://wa.me/33632519053` |
| `META_PAGE_ID` | Beo Facebook Page id (never Liba) |
| `META_PAGE_ACCESS_TOKEN` | Beo Page token |
| `META_IG_USER_ID` | Beo Instagram Business id |
| `SOCIAL_DRY_RUN` | `1` until Meta tokens; then `0` |

Then Deploy. Beo OS should proxy `/api/beo-agents` to `http://127.0.0.1:8788`.

Hermes for עדי is built from `bundled/social-beo` into the image. Runtime writes go to the Docker volume `social-home`. The old path `agents/social-beo` is not in git (it was a bind-mount leftover that blocked `git pull`).
