# Air-Gapped Deployment Guide

> **Despliegue completamente offline** para entornos con requisitos estrictos de seguridad, cumplimiento normativo (SOC 2, HIPAA, PCI-DSS), o infraestructura aislada.

---

## 📋 Requisitos Previos

- **Docker** 24+ o **Podman** 4+
- **Kubernetes** 1.28+ (para Helm)
- **Acceso a registry mirror interno** (Harbor, Nexus, o Docker Registry)
- **Ollama** (opcional — para AI local)
- **Licencia offline** generada con `zenic-cli`

---

## 🔒 Modo Air-Gapped

### 1. Variables de Entorno

```bash
# Activar modo air-gapped
export WFD_AIRGAP_MODE=true

# Permitir AI local (Ollama) en modo offline
export WFD_AIRGAP_ALLOW_LOCAL_AI=true

# Espejo de imágenes Docker interno
export WFD_AIRGAP_REGISTRY_MIRROR=registry.internal:5000

# Ruta al archivo de licencia offline
export WFD_AIRGAP_LICENSE_FILE=/etc/zenic-flijo/license.json
```

### 2. Docker Compose Air-Gapped

```yaml
# docker-compose.airgap.yml
version: "3.8"
services:
  app:
    image: registry.internal:5000/zenicflijo/app:latest
    environment:
      - WFD_AIRGAP_MODE=true
      - WFD_AIRGAP_ALLOW_LOCAL_AI=true
      - WFD_AIRGAP_LICENSE_FILE=/etc/zenic-flijo/license.json
      - WFD_OLLAMA_ENABLED=true
      - WFD_OLLAMA_URL=http://ollama:11434
    volumes:
      - ./license.json:/etc/zenic-flijo/license.json:ro
      - data:/root/.workflow_determinista
    ports:
      - "8080:8080"
      - "8081:8081"
    networks:
      - internal

  ollama:
    image: registry.internal:5000/ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    networks:
      - internal

  postgres:
    image: registry.internal:5000/postgres:16
    environment:
      POSTGRES_DB: zenic_flijo
      POSTGRES_USER: zenic
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - internal

  redis:
    image: registry.internal:5000/redis:7-alpine
    networks:
      - internal

volumes:
  data:
  ollama-models:
  postgres-data:

networks:
  internal:
    driver: bridge
    internal: true  # Sin acceso a internet
```

### 3. Helm Air-Gapped Values

```yaml
# helm/zenic-flijo/values.airgap.yaml
global:
  environment: production
  region: internal

app:
  extraEnv:
    - name: WFD_AIRGAP_MODE
      value: "true"
    - name: WFD_AIRGAP_ALLOW_LOCAL_AI
      value: "true"
    - name: WFD_OLLAMA_ENABLED
      value: "true"
    - name: WFD_OLLAMA_URL
      value: "http://ollama:11434"

image:
  repository: registry.internal:5000/zenicflijo/app
  tag: latest
  pullPolicy: IfNotPresent

ingress:
  enabled: true
  className: nginx
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
  hosts:
    - host: zenic-flijo.internal
      paths:
        - path: /
          pathType: Prefix

secrets:
  sessionSecret: ""  # Set via sealed-secrets
  encryptionMasterKey: ""

ollama:
  enabled: true
  image: registry.internal:5000/ollama/ollama:latest
  models:
    - llama3.2
    - nomic-embed-text
```

### 4. Generar Licencia Offline

```bash
# Usar el CLI para generar licencia offline
zenic-cli airgap license create \
  --customer "Empresa S.A." \
  --license-key "XXXX-XXXX-XXXX-XXXX" \
  --expiry-days 365 \
  --output /etc/zenic-flijo/license.json

# Verificar licencia
zenic-cli airgap license verify
```

---

## 📦 Preparación del Registry Mirror

### 1. Configurar Harbor/Nexus como Registry Mirror

```bash
# Pull desde registry público (con internet)
docker pull zenicflijo/app:latest
docker pull postgres:16
docker pull redis:7-alpine
docker pull ollama/ollama:latest

# Taggear para registry interno
docker tag zenicflijo/app:latest registry.internal:5000/zenicflijo/app:latest
docker tag postgres:16 registry.internal:5000/postgres:16
docker tag redis:7-alpine registry.internal:5000/redis:7-alpine
docker tag ollama/ollama:latest registry.internal:5000/ollama/ollama:latest

# Push a registry interno
docker push registry.internal:5000/zenicflijo/app:latest
docker push registry.internal:5000/postgres:16
docker push registry.internal:5000/redis:7-alpine
docker push registry.internal:5000/ollama/ollama:latest
```

### 2. Script de Sincronización

```bash
#!/bin/bash
# scripts/sync-airgap-images.sh
# Ejecutar en máquina con internet, luego transferir a air-gapped

REGISTRY="registry.internal:5000"
IMAGES=(
  "zenicflijo/app:latest"
  "postgres:16"
  "redis:7-alpine"
  "ollama/ollama:latest"
)

for image in "${IMAGES[@]}"; do
  echo "📥 Pulling $image..."
  docker pull "$image"
  
  LOCAL_TAG="$REGISTRY/$image"
  echo "🏷️ Tagging $image → $LOCAL_TAG"
  docker tag "$image" "$LOCAL_TAG"
  
  echo "📤 Pushing $LOCAL_TAG..."
  docker push "$LOCAL_TAG"
done

echo "✅ All images synced to $REGISTRY"
```

---

## 🌐 Topología de Red Air-Gapped

```
┌─────────────────────────────────────┐
│       Red Aislada (10.0.0.0/8)      │
│                                      │
│  ┌──────────┐  ┌──────────────────┐ │
│  │ Ollama    │  │ Zenic-Flijo App  │ │
│  │ (AI local)│  │ Puerto 8080/8081 │ │
│  └────┬─────┘  └────────┬─────────┘ │
│       │                 │           │
│  ┌────┴─────┐  ┌────────┴─────────┐│
│  │ PostgreSQL │  │     Redis       ││
│  │  Puerto 5432│  │   Puerto 6379  ││
│  └──────────┘  └──────────────────┘ │
│                                      │
│  ┌──────────────────────────────┐   │
│  │  Volumen: /root/.workflow... │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
         ▲ Sin acceso a internet
         │
    ┌────┴────┐
    │  Cliente │
    │  LAN     │
    └─────────┘
```

---

## 🔐 Conectores en Modo Air-Gapped

| Tipo | Estado | Ejemplos |
|------|--------|---------|
| **Online** ❌ | Desactivados | OpenAI, Anthropic, SendGrid, Twilio, GitHub, AWS S3 |
| **Local** ✅ | Activados | RUV, SAT México, PIX Brazil, TOTVS, Vault |
| **Red Local** ✅ | Activados | PostgreSQL, MySQL, MongoDB, Redis (infraestructura local) |

---

## ✅ Verificación de Air-Gapped Readiness

```bash
# Verificar estado completo
zenic-cli airgap check

# Salida esperada:
# ✅ Modo air-gapped: ACTIVADO
# ✅ Sin acceso a internet: OK
# ✅ Licencia offline: VÁLIDA (340 días restantes)
# ✅ Registry mirror: configurado (registry.internal:5000)
# ✅ AI Local: disponible (Ollama v0.5.0)
# ✅ Base de datos local: conectada
# ✅ Almacenamiento: escribible
# ⚠️ Conectores cloud desactivados: 44
# ✅ Conectores locales activos: 5
```

---

## 📊 Conexiones por Defecto en Modo Air-Gapped

| Servicio | Puerto | Protocolo | Notas |
|----------|--------|-----------|-------|
| PostgreSQL | 5432 | TCP | Base de datos |
| Redis | 6379 | TCP | Cache y pub/sub |
| Ollama | 11434 | HTTP | AI local |
| Vault | 8200 | HTTP | Gestión de secretos |
| Web | 8080 | HTTP/HTTPS | API REST + UI |
| Webhook | 8081 | HTTP | Webhooks entrantes |

---

## 🔄 Estrategia de Actualización Offline

1. **Pull con internet** → `docker pull zenicflijo/app:NEW_TAG`
2. **Transferir** → Guardar como tar: `docker save zenicflijo/app:NEW_TAG > app.tar`
3. **Transferir a air-gapped** → USB, SCP, o almacenamiento externo
4. **Cargar en air-gapped** → `docker load < app.tar`
5. **Taggear a registry mirror** → `docker tag ... registry.internal:5000/...`
6. **Push a registry mirror** → `docker push ...`
7. **Deploy** → `helm upgrade zenic-flijo helm/zenic-flijo/ -f values.airgap.yaml`

---

## 🧪 Testing en Modo Air-Gapped

```bash
# Ejecutar tests de verificación air-gapped
python -m pytest src/tests/test_airgap.py -v

# Probar conectores locales
python -c "from src.config.airgap import get_instance; print(get_instance().validate())"
```
