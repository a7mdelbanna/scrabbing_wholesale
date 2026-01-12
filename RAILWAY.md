# Deploy to Railway

One-click deployment guide for Railway.

## Quick Deploy (5 minutes)

### Step 1: Create Railway Account
Go to [railway.app](https://railway.app) and sign up with GitHub.

### Step 2: Create New Project
1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose your `scrabing` repository

### Step 3: Add PostgreSQL
1. In your project, click **"New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway auto-creates the database

### Step 4: Add Redis
1. Click **"New"** again
2. Select **"Database"** → **"Add Redis"**

### Step 5: Configure Environment Variables
Click on your main service, go to **"Variables"** tab, and add:

```env
# Database (auto-linked)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Redis (auto-linked)
REDIS_URL=${{Redis.REDIS_URL}}

# Security (generate these)
ENCRYPTION_KEY=<generate with: openssl rand -hex 32>
SECRET_KEY=<generate with: openssl rand -hex 32>

# App Config
ENVIRONMENT=production
LOG_LEVEL=INFO

# Scraper Credentials
BEN_SOLIMAN_USERNAME=your_username
BEN_SOLIMAN_PASSWORD=your_password
TAGER_ELSAADA_USERNAME=your_username
TAGER_ELSAADA_PASSWORD=your_password
```

### Step 6: Deploy
Railway auto-deploys when you push to GitHub. Or click **"Deploy"** manually.

### Step 7: Get Your URL
After deployment, Railway gives you a URL like:
```
https://scraping-api-production.up.railway.app
```

---

## Multi-Service Setup (Optional)

For background workers and scheduler, create additional services:

### Add Worker Service
1. Click **"New"** → **"Empty Service"**
2. Connect same GitHub repo
3. Set **Start Command**:
   ```
   celery -A src.workers.celery_app worker --loglevel=info
   ```
4. Add same environment variables

### Add Scheduler Service
1. Click **"New"** → **"Empty Service"**
2. Connect same GitHub repo
3. Set **Start Command**:
   ```
   python -m src.scheduler.run
   ```
4. Add same environment variables

---

## Architecture on Railway

```
┌─────────────────────────────────────────┐
│              Railway Project            │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────┐    ┌─────────────┐    │
│  │   API       │    │   Worker    │    │
│  │  (web)      │    │  (worker)   │    │
│  └──────┬──────┘    └──────┬──────┘    │
│         │                  │            │
│         └────────┬─────────┘            │
│                  │                      │
│         ┌───────┴───────┐              │
│         │               │              │
│    ┌────┴────┐    ┌────┴────┐         │
│    │PostgreSQL│    │  Redis  │         │
│    └─────────┘    └─────────┘         │
│                                         │
└─────────────────────────────────────────┘
```

---

## Estimated Costs

| Service | Usage | Cost |
|---------|-------|------|
| API | Always on | ~$5/mo |
| PostgreSQL | 1GB | ~$5/mo |
| Redis | 25MB | ~$0-3/mo |
| Worker | Always on | ~$5/mo |
| **Total** | | **~$15-20/mo** |

*Railway has a $5 free tier credit per month*

---

## Useful Commands

### View Logs
```bash
railway logs
```

### Open Shell
```bash
railway shell
```

### Run Migrations
```bash
railway run alembic upgrade head
```

### Connect to Database
```bash
railway connect postgres
```

---

## Environment Variable Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `ENCRYPTION_KEY` | Yes | For encrypting credentials |
| `SECRET_KEY` | Yes | For JWT/sessions |
| `BEN_SOLIMAN_USERNAME` | Yes | Scraper credential |
| `BEN_SOLIMAN_PASSWORD` | Yes | Scraper credential |
| `LOG_LEVEL` | No | INFO, DEBUG, WARNING |

---

## Troubleshooting

### Build Fails
- Check Dockerfile syntax
- Ensure all dependencies in requirements.txt

### Database Connection Error
- Verify `DATABASE_URL` uses `${{Postgres.DATABASE_URL}}`
- Check PostgreSQL service is running

### Redis Connection Error
- Verify `REDIS_URL` uses `${{Redis.REDIS_URL}}`
- Check Redis service is running

### Health Check Fails
- Ensure `/api/v1/system/health` endpoint works
- Check logs for startup errors

---

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
