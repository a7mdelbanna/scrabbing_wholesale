# Deployment Guide

This guide covers deploying the Competitor Price Scraping API to production.

## Quick Start (DigitalOcean/VPS)

### 1. Create a VPS
- DigitalOcean Droplet: Ubuntu 22.04, 2GB RAM, $12/mo
- Or any VPS with Docker support

### 2. Connect to Server
```bash
ssh root@your-server-ip
```

### 3. Install Docker
```bash
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker
```

### 4. Clone Repository
```bash
git clone https://github.com/yourusername/scrabing.git
cd scrabing
```

### 5. Configure Environment
```bash
cp .env.production.example .env.production
nano .env.production  # Edit with your values
```

**Important settings to change:**
- `POSTGRES_PASSWORD` - Strong database password
- `ENCRYPTION_KEY` - Generate with `openssl rand -hex 32`
- `SECRET_KEY` - Generate with `openssl rand -hex 32`
- Scraper credentials for each app

### 6. Deploy
```bash
chmod +x deploy.sh
./deploy.sh setup
./deploy.sh start
```

### 7. Verify
```bash
./deploy.sh status
curl http://localhost:8000/api/v1/system/health
```

---

## Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         NGINX                                │
│                    (Reverse Proxy)                           │
│                   Port 80/443                                │
└────────────────┬──────────────────┬─────────────────────────┘
                 │                  │
                 ▼                  ▼
┌────────────────────┐  ┌────────────────────┐
│    API Server      │  │    Dashboard       │
│   (FastAPI)        │  │   (FastAPI)        │
│   Port 8000        │  │   Port 5000        │
└────────┬───────────┘  └────────┬───────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌────────────────┐    ┌────────────────┐
│   PostgreSQL   │    │     Redis      │
│   Port 5432    │    │   Port 6379    │
└────────────────┘    └────────────────┘
         ▲                       ▲
         │                       │
┌────────┴───────────────────────┴────────┐
│                                          │
│   ┌──────────────┐   ┌──────────────┐   │
│   │   Worker     │   │  Scheduler   │   │
│   │  (Celery)    │   │ (APScheduler)│   │
│   └──────────────┘   └──────────────┘   │
│                                          │
└──────────────────────────────────────────┘
```

---

## Deployment Commands

```bash
# Initial setup
./deploy.sh setup

# Start services
./deploy.sh start

# Start with Nginx reverse proxy
./deploy.sh start-nginx

# Stop all services
./deploy.sh stop

# View logs
./deploy.sh logs           # All services
./deploy.sh logs api       # Specific service

# Backup database
./deploy.sh backup

# Restore database
./deploy.sh restore backups/db_backup_20240115.sql.gz

# Update application
./deploy.sh update

# Check status
./deploy.sh status

# Shell access
./deploy.sh shell api
```

---

## SSL/HTTPS Setup

### Option 1: Certbot (Let's Encrypt)
```bash
# Install certbot
apt install certbot python3-certbot-nginx

# Get certificate
certbot --nginx -d api.yourdomain.com -d dashboard.yourdomain.com

# Auto-renewal is configured automatically
```

### Option 2: Manual SSL
1. Place certificates in `nginx/ssl/`:
   - `fullchain.pem`
   - `privkey.pem`
2. Uncomment SSL lines in `nginx/nginx.conf`
3. Restart: `./deploy.sh restart`

---

## Scaling

### Horizontal Scaling (Multiple Workers)
```yaml
# In docker-compose.prod.yml
worker:
  deploy:
    replicas: 3
```

### Vertical Scaling
Upgrade your VPS to more RAM/CPU as needed.

### Database Scaling
For high load, consider:
- AWS RDS PostgreSQL
- DigitalOcean Managed Database
- Read replicas

---

## Monitoring

### Health Endpoints
- API: `http://localhost:8000/api/v1/system/health`
- Dashboard: `http://localhost:5000/`

### Logs
```bash
# Real-time logs
./deploy.sh logs

# Docker logs
docker logs scraping_api -f --tail 100
```

### Resource Usage
```bash
docker stats
```

---

## Backup Strategy

### Automated Backups
Add to crontab:
```bash
crontab -e
# Add:
0 2 * * * /path/to/scrabing/deploy.sh backup
```

### Manual Backup
```bash
./deploy.sh backup
```

### Restore
```bash
./deploy.sh restore backups/db_backup_TIMESTAMP.sql.gz
```

---

## Troubleshooting

### Service won't start
```bash
# Check logs
./deploy.sh logs api

# Check container status
docker-compose -f docker-compose.prod.yml ps

# Restart specific service
docker-compose -f docker-compose.prod.yml restart api
```

### Database connection issues
```bash
# Check if DB is healthy
docker-compose -f docker-compose.prod.yml exec db pg_isready

# Check connection
docker-compose -f docker-compose.prod.yml exec api python -c "from src.database.connection import engine; print('OK')"
```

### Out of memory
```bash
# Check memory usage
docker stats

# Increase swap (temporary)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```

---

## Security Checklist

- [ ] Change default passwords in `.env.production`
- [ ] Generate strong `ENCRYPTION_KEY` and `SECRET_KEY`
- [ ] Enable firewall (ufw)
- [ ] Configure SSL/HTTPS
- [ ] Disable root SSH login
- [ ] Set up fail2ban
- [ ] Regular security updates

### Firewall Setup
```bash
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable
```

---

## Platform-Specific Guides

### Railway
1. Connect GitHub repo
2. Add PostgreSQL service
3. Add Redis service
4. Set environment variables
5. Deploy

### Render
1. Create Web Service from repo
2. Add PostgreSQL database
3. Add Redis instance
4. Configure environment
5. Deploy

### AWS ECS
1. Push image to ECR
2. Create ECS cluster
3. Create task definition
4. Set up RDS PostgreSQL
5. Set up ElastiCache Redis
6. Configure ALB

---

## Support

For issues, check:
1. Container logs: `./deploy.sh logs`
2. Health endpoint: `/api/v1/system/health`
3. Database connectivity
4. Redis connectivity
