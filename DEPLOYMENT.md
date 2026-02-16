# agentgw Deployment Guide

This guide covers deploying agentgw for production use.

## Table of Contents

- [Docker Deployment](#docker-deployment)
- [Systemd Service](#systemd-service)
- [Environment Configuration](#environment-configuration)
- [Security Best Practices](#security-best-practices)
- [Monitoring & Health Checks](#monitoring--health-checks)
- [Scaling Considerations](#scaling-considerations)

---

## Docker Deployment

### Dockerfile

Create `Dockerfile` in the project root:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY skills/ ./skills/
COPY config/ ./config/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create data directory
RUN mkdir -p /app/data

# Expose web UI port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run web server
CMD ["uvicorn", "agentgw.interfaces.web.app:create_app", "--host", "0.0.0.0", "--port", "8080", "--factory"]
```

### docker-compose.yml

For local development or single-server deployment:

```yaml
version: '3.8'

services:
  agentgw:
    build: .
    ports:
      - "8080:8080"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - XAI_API_KEY=${XAI_API_KEY:-}
      - AGENTGW_API_KEY=${AGENTGW_API_KEY}  # API authentication
      - AGENTGW_LLM__PROVIDER=${LLM_PROVIDER:-openai}
      - AGENTGW_LLM__MODEL=${LLM_MODEL:-gpt-4o-mini}
    volumes:
      - ./data:/app/data  # Persist SQLite DB and ChromaDB
      - ./skills:/app/skills  # Hot-reload skills
      - ./config:/app/config  # Configuration files
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Optional: Webhook receiver for testing
  webhook-receiver:
    image: jmalloc/echo-server
    ports:
      - "8081:8080"
```

### Build and Run

```bash
# Build image
docker build -t agentgw:latest .

# Run with environment file
docker run -d \
  --name agentgw \
  -p 8080:8080 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  agentgw:latest

# Or use docker-compose
docker-compose up -d

# View logs
docker logs -f agentgw

# Check health
curl http://localhost:8080/health
```

---

## Systemd Service

For deploying directly on Linux servers.

### Create Service File

`/etc/systemd/system/agentgw.service`:

```ini
[Unit]
Description=agentgw AI Agent Framework
After=network.target

[Service]
Type=simple
User=agentgw
Group=agentgw
WorkingDirectory=/opt/agentgw
Environment="PATH=/opt/agentgw/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/agentgw/.env
ExecStart=/opt/agentgw/.venv/bin/uvicorn agentgw.interfaces.web.app:create_app --host 0.0.0.0 --port 8080 --factory
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/agentgw/data

[Install]
WantedBy=multi-user.target
```

### Setup Steps

```bash
# Create dedicated user
sudo useradd -r -s /bin/false agentgw

# Create application directory
sudo mkdir -p /opt/agentgw
sudo chown agentgw:agentgw /opt/agentgw

# Deploy application (as agentgw user)
cd /opt/agentgw
git clone <your-repo> .
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Create data directory
mkdir -p data
sudo chown -R agentgw:agentgw /opt/agentgw

# Copy environment file
sudo cp .env.example /opt/agentgw/.env
sudo chown agentgw:agentgw /opt/agentgw/.env
sudo chmod 600 /opt/agentgw/.env
# Edit /opt/agentgw/.env with your API keys

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable agentgw
sudo systemctl start agentgw

# Check status
sudo systemctl status agentgw
sudo journalctl -u agentgw -f
```

### Nginx Reverse Proxy

`/etc/nginx/sites-available/agentgw`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # For SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }

    # Health check endpoint (no auth required)
    location /health {
        proxy_pass http://127.0.0.1:8080;
        access_log off;
    }
}
```

Enable and restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/agentgw /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Environment Configuration

### Required Environment Variables

```bash
# API Keys (at least one LLM provider required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...  # Optional
XAI_API_KEY=xai-...            # Optional

# Authentication (REQUIRED for production)
AGENTGW_API_KEY=your-secure-random-key-here

# LLM Configuration
AGENTGW_LLM__PROVIDER=openai  # openai, anthropic, xai
AGENTGW_LLM__MODEL=gpt-4o-mini

# Agent Configuration
AGENTGW_AGENT__MAX_ITERATIONS=10
AGENTGW_AGENT__MAX_ORCHESTRATION_DEPTH=3

# Storage Paths (relative to project root)
AGENTGW_STORAGE__SQLITE_PATH=data/agentgw.db
AGENTGW_STORAGE__CHROMA_PATH=data/chroma
AGENTGW_STORAGE__LOG_DIR=data/logs

# Webhook Configuration
AGENTGW_WEBHOOK_MAX_RETRIES=3
AGENTGW_WEBHOOK_TIMEOUT=30
```

### Generating Secure API Key

```bash
# Generate a random 32-character API key
openssl rand -hex 32

# Or use Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Security Best Practices

### 1. API Key Authentication

**Always enable API key authentication in production:**

```bash
export AGENTGW_API_KEY=your-secure-key
```

Clients must include the API key in requests:

```bash
curl -H "Authorization: Bearer your-secure-key" \
     http://your-domain.com/api/skills
```

### 2. HTTPS/TLS

- Use Let's Encrypt for free SSL certificates
- Redirect all HTTP traffic to HTTPS
- Use strong TLS configuration (TLS 1.2+)

### 3. File Permissions

```bash
# Restrict .env file
chmod 600 /opt/agentgw/.env

# Restrict data directory
chown -R agentgw:agentgw /opt/agentgw/data
chmod 700 /opt/agentgw/data
```

### 4. Firewall Rules

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP (redirects to HTTPS)
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### 5. Rate Limiting

Add to Nginx config:

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

location /api/ {
    limit_req zone=api_limit burst=20 nodelay;
    # ... rest of proxy config
}
```

### 6. Secrets Management

For production, use a secrets manager:

- **AWS**: AWS Secrets Manager or Parameter Store
- **GCP**: Google Secret Manager
- **Azure**: Azure Key Vault
- **Kubernetes**: Sealed Secrets or External Secrets Operator

Example with AWS Secrets Manager:

```bash
# Store secret
aws secretsmanager create-secret \
    --name agentgw/api-keys \
    --secret-string file://secrets.json

# Retrieve in startup script
export OPENAI_API_KEY=$(aws secretsmanager get-secret-value \
    --secret-id agentgw/api-keys \
    --query SecretString --output text | jq -r .OPENAI_API_KEY)
```

---

## Monitoring & Health Checks

### Health Check Endpoint

```bash
curl http://localhost:8080/health

# Response:
{
  "status": "healthy",
  "version": "0.1.0",
  "provider": "openai",
  "model": "gpt-4o-mini"
}
```

### Prometheus Metrics (Future Enhancement)

Add to `requirements.txt`:
```
prometheus-client>=0.19
```

Example metrics endpoint (to be implemented):

```python
from prometheus_client import Counter, Histogram, generate_latest

requests_total = Counter('agentgw_requests_total', 'Total requests', ['skill', 'status'])
request_duration = Histogram('agentgw_request_duration_seconds', 'Request duration')

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### Log Aggregation

**Using journald (systemd):**

```bash
# View logs
journalctl -u agentgw -f

# Filter by time
journalctl -u agentgw --since "1 hour ago"

# Export to file
journalctl -u agentgw --since today > agentgw.log
```

**Using Docker logging driver:**

```yaml
# docker-compose.yml
services:
  agentgw:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## Scaling Considerations

### Single Server Limits

- SQLite: Good for <1000 requests/day
- ChromaDB: Handles 10K-100K documents efficiently
- Bottleneck: LLM API calls (not application itself)

### Horizontal Scaling

For high traffic, multiple instances can run behind a load balancer:

**Shared State Requirements:**
- Replace SQLite with PostgreSQL or MySQL
- Replace local ChromaDB with Qdrant or Weaviate (vector DB services)
- Use Redis for session state (if implementing session sticky)

**Load Balancer:**

```nginx
upstream agentgw_backend {
    least_conn;
    server 10.0.1.10:8080;
    server 10.0.1.11:8080;
    server 10.0.1.12:8080;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    location / {
        proxy_pass http://agentgw_backend;
        # ... proxy settings
    }
}
```

### Kubernetes Deployment

Example `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentgw
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agentgw
  template:
    metadata:
      labels:
        app: agentgw
    spec:
      containers:
      - name: agentgw
        image: agentgw:latest
        ports:
        - containerPort: 8080
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: agentgw-secrets
              key: openai-api-key
        - name: AGENTGW_API_KEY
          valueFrom:
            secretKeyRef:
              name: agentgw-secrets
              key: api-key
        volumeMounts:
        - name: data
          mountPath: /app/data
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: agentgw-data
---
apiVersion: v1
kind: Service
metadata:
  name: agentgw
spec:
  selector:
    app: agentgw
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: LoadBalancer
```

---

## Backup & Recovery

### Backup Script

```bash
#!/bin/bash
# /opt/agentgw/backup.sh

BACKUP_DIR="/opt/backups/agentgw"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup SQLite database
cp /opt/agentgw/data/agentgw.db $BACKUP_DIR/agentgw_$TIMESTAMP.db

# Backup ChromaDB
tar -czf $BACKUP_DIR/chroma_$TIMESTAMP.tar.gz /opt/agentgw/data/chroma

# Backup configurations
tar -czf $BACKUP_DIR/config_$TIMESTAMP.tar.gz /opt/agentgw/config

# Keep only last 30 days
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: $TIMESTAMP"
```

Add to cron:

```bash
# Run daily at 2 AM
0 2 * * * /opt/agentgw/backup.sh >> /var/log/agentgw-backup.log 2>&1
```

---

## Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u agentgw -n 100 --no-pager

# Verify permissions
ls -la /opt/agentgw/data

# Test manually
cd /opt/agentgw
source .venv/bin/activate
uvicorn agentgw.interfaces.web.app:create_app --factory
```

### High memory usage

ChromaDB can use significant memory. Monitor with:

```bash
docker stats agentgw  # For Docker
ps aux | grep agentgw  # For systemd
```

### Webhook delivery failures

Check webhook logs:

```bash
grep "webhook" /opt/agentgw/data/logs/agentgw.log
```

Verify webhook endpoint is accessible:

```bash
curl -X POST http://your-webhook-url \
     -H "Content-Type: application/json" \
     -d '{"test": "data"}'
```

---

## Support & Resources

- **Documentation**: README.md
- **Issues**: GitHub Issues
- **Configuration**: config/settings.yaml
- **Logs**: data/logs/ or journalctl

For production support, consider:
- Setting up monitoring alerts
- Implementing log aggregation
- Regular backups
- Disaster recovery plan
