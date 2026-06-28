---
name: container-runtime
description: Docker container, docker-compose, deployment configuration
load: on-demand
tokens: ~130
---

# Container Runtime

## Module: root-level Docker configs
Containerization and deployment infrastructure.

### Key Files
- `Dockerfile` - Main application container
- `docker-compose.yml` - Multi-service orchestration
- `deploy/` - Deployment configurations
- `helm/` - Kubernetes Helm charts
- `nginx/` - Nginx reverse proxy configs
- `scripts/` - Deployment scripts

### Services (docker-compose)
- App server (Flask/Python)
- Frontend (Vite/React)
- Nginx (reverse proxy)
- Database (SQLite/Postgres)

### Usage
```bash
docker-compose up -d
helm install zenic-flujo ./helm/
```
