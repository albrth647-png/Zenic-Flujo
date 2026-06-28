# 🚀 Zenic-Flijo — Despliegue

## 📋 Requisitos

| Componente | Versión | Propósito |
|-----------|---------|-----------|
| Kubernetes | 1.28+ | Orquestación de contenedores |
| Helm | 3.12+ | Package manager |
| Ingress Controller | nginx | Enrutamiento HTTP |
| cert-manager | 1.14+ | TLS automático |
| Prometheus Operator | (opcional) | ServiceMonitor |
| Istio | 1.21+ | (opcional) Service Mesh |

## 📦 Métodos de despliegue

### 1. Helm Chart (recomendado)

```bash
# Agregar repositorio (próximamente)
# helm repo add zenic-flujo https://helm.zenic-flujo.io

# Instalar
helm install zenic-flujo ./deploy/helm/zenic-flujo \
  --namespace zenic-flujo \
  --create-namespace \
  --set secrets.WFD_SESSION_SECRET="$(openssl rand -hex 32)" \
  --set secrets.WFD_LICENSE_SECRET="$(openssl rand -hex 32)" \
  --set secrets.WFD_ENCRYPTION_MASTER_KEY="$(openssl rand -hex 32)" \
  --set ingress.hosts[0].host="app.zenic-flujo.io"

# Verificar
kubectl get pods -n zenic-flujo -w

# Obtener URL
kubectl get ingress -n zenic-flujo
```

### 2. K8s Manifests (Kustomize)

```bash
# Configurar namespace y recursos
kubectl apply -k deploy/k8s/

# Verificar estado
kubectl get all -n zenic-flujo
```

### 3. Docker Compose (desarrollo)

```bash
# Crear archivo .env con config local
cat > .env << EOF
WFD_SESSION_SECRET=cambio-en-produccion
WFD_LICENSE_SECRET=cambio-en-produccion
WFD_PRODUCTION=false
EOF

# Iniciar stack
docker compose up -d

# Ver logs
docker compose logs -f zenic-flujo
```

### 4. Docker standalone

```bash
docker run -d \
  --name zenic-flujo \
  -p 8080:8080 \
  -p 8081:8081 \
  -e WFD_SESSION_SECRET="$(openssl rand -hex 32)" \
  -e WFD_SESSION_SECURE=false \
  -v zenic-data:/app/data \
  ghcr.io/albrth647-png/zenic-flujo:latest
```

## ⚙️ Configuración

### Variables de entorno esenciales

| Variable | Descripción | Obligatoria |
|----------|-------------|-------------|
| `WFD_SESSION_SECRET` | Clave para firmar sesiones (mín. 32 bytes hex) | ✅ |
| `WFD_LICENSE_SECRET` | Clave para validar licencias | ✅ |
| `WFD_ENCRYPTION_MASTER_KEY` | Clave maestra de cifrado (BYOK, 32 bytes hex) | ❌ |
| `WFD_POSTGRES_URL` | URL de PostgreSQL | ❌ (usa SQLite por defecto) |
| `WFD_REDIS_URL` | URL de Redis (sesiones, caché) | ❌ |
| `WFD_PRODUCTION` | `true` en producción | ✅ |

### Persistencia

- **SQLite**: `/app/data/workflow.db` (usar PersistentVolumeClaim)
- **PostgreSQL**: Recomendado para HA (configurar vía `WFD_POSTGRES_URL`)
- **Redis**: Sesiones y caché distribuidas (configurar vía `WFD_REDIS_URL`)

## 📊 HPA (Auto Scaling)

El HPA escala automáticamente entre 2 y 10 réplicas basado en:

- **CPU**: >70% de utilización → scale up
- **Memoria**: >80% de utilización → scale up
- **Comportamiento**: Scale up rápido (100%/15s), scale down lento (25%/60s)

```bash
# Ver estado del HPA
kubectl get hpa -n zenic-flujo -w

# Forzar escala manual
kubectl scale deployment zenic-flujo -n zenic-flujo --replicas=5
```

## 🔐 Service Mesh (Istio)

### Componentes instalados:

| Recurso | Propósito |
|---------|-----------|
| Gateway | TLS termination en el mesh ingress |
| VirtualService | Routing, timeouts, retries |
| DestinationRule | Circuit breaker, mTLS, load balancing |
| PeerAuthentication | mTLS STRICT entre servicios |

```bash
# Aplicar mesh
kubectl apply -f deploy/istio/

# Verificar mTLS
istioctl authn tls-check zenic-flujo.zenic-flujo.svc.cluster.local
```

## 📈 Monitoreo

### Prometheus + Grafana (recomendado)

```bash
# Aplicar ServiceMonitor
kubectl apply -f deploy/helm/zenic-flujo/templates/servicemonitor.yaml

# Métricas disponibles en /metrics
kubectl port-forward svc/zenic-flujo 8080:8080 -n zenic-flujo
curl http://localhost:8080/metrics
```

### Dashboards recomendados:

- **Go Runtime**: `grafana-dashboard-go`
- **Flask App**: `grafana-dashboard-flask`
- **Kubernetes**: Node Exporter Full

## 🔄 Actualización

```bash
# Helm
helm upgrade zenic-flujo ./deploy/helm/zenic-flujo \
  --namespace zenic-flujo \
  -f values-prod.yaml

# Kustomize
kubectl apply -k deploy/k8s/
```

## 🐛 Troubleshooting

| Problema | Solución |
|----------|----------|
| Pod CrashLoopBackOff | `kubectl logs -n zenic-flujo deployment/zenic-flujo` |
| HPA no escala | `kubectl describe hpa -n zenic-flujo` |
| TLS certificate error | `kubectl describe certificate -n zenic-flujo` |
| Base de datos corrupta | Restaurar backup de `/app/data/workflow.db` |
| Istio mTLS errors | `istioctl analyze -n zenic-flujo` |

## 📚 Referencias

- [Documentación de Zenic-Flijo](https://github.com/albrth647-png/Zenic-Flijo)
- [Helm Docs](https://helm.sh/docs/)
- [Istio Docs](https://istio.io/latest/docs/)
- [cert-manager Docs](https://cert-manager.io/docs/)
