---
name: deployment
description: Deployment - K8s, Helm, Docker, CI/CD, monitoring
load: on-demand
tokens: ~150
---

# Deployment

## Infrastructure
Production deployment infrastructure for Zenic-Flujo.

### Deployment Options
- **Docker Compose**: Local/development deployment
- **Kubernetes**: Production with Helm charts
- **Nginx**: Reverse proxy and load balancing
- **Grafana**: Monitoring dashboards
- **Istio**: Service mesh

### Directory Structure
- `deploy/` - Deployment configs
  - `docker/` - Dockerfiles per service
  - `k8s/` - Kubernetes manifests
  - `grafana/` - Dashboard definitions
  - `istio/` - Service mesh config
  - `helm/` - Helm charts
- `nginx/` - Nginx configuration
- `installer/` - Installation scripts

### Health Checks
```bash
docker-compose ps
curl http://localhost:5000/health
helm test zenic-flujo
```
