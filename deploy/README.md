# Deploy Beo Agents on beo-systems-1

Private repo only: `github.com/ceo7815/beo-agents`. Never ceo-digital or Hub.
Do not merge into Titatu / Mochka / Hub agent folders.

## On the server

```bash
cd /opt   # or the Cloud site folder you choose — not Titatu.agents
git clone https://github.com/ceo7815/beo-agents.git
cd beo-agents
cp agents/leads-beo/.env.example agents/leads-beo/.env
cp agents/social-beo/.env.example agents/social-beo/.env
# fill both .env files on the server (never commit them)
# copy Gmail secrets into agents/leads-beo/secrets/ if sending mail
docker compose up -d --build
docker compose logs -f control
```

Control API listens on `127.0.0.1:8788` on the host. Beo OS (`os.beosystem.com`) should proxy `/api/beo-agents` there.

Containers: `beo-control` (שי / Telegram / pipeline), `beo-social` (עדי / Hermes).
