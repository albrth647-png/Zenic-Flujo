# ⚙️ Workflow Determinista

**Automatización offline para tu negocio. Sin internet, sin mensualidades.**

Workflow Determinista es un sistema de automatización de procesos de negocio que instalas en tu propia computadora, pagas una sola vez, y funciona 100% offline.

## 🚀 Instalación Rápida

### Opción 1: Ejecutable (Windows/Linux)
1. Descarga el instalador desde [GitHub Releases](https://github.com/tuusuario/workflow-determinista/releases)
2. Haz doble clic en `WorkflowDeterminista_v1.0.exe`
3. Sigue las instrucciones del instalador
4. Abre `http://localhost:8080` en tu navegador

### Opción 2: Desde código fuente (Python)

**Requisitos:** Python 3.10+

```bash
# Clonar
git clone https://github.com/tuusuario/workflow-determinista.git
cd workflow-determinista

# Instalar dependencias
pip install -r requirements.txt

# Iniciar
python src/main.py
```

## 🖥️ Uso

1. Abre `http://localhost:8080` en tu navegador
2. Inicia sesión con tu contraseña de administrador
3. Usa el **Chat** para crear workflows con lenguaje natural
4. Monitorea tus automatizaciones en el **Dashboard**
5. Configura SMTP, webhooks y más en **Configuración**

## 🧰 Herramientas incluidas

| Herramienta | Descripción |
|---|---|
| **CRM** | Gestión de clientes y pipeline de ventas |
| **Facturación** | Generación y seguimiento de facturas |
| **Inventario** | Control de stock con alertas automáticas |
| **Notificaciones** | Emails automáticos vía SMTP |
| **Auto Pilot** | Plantillas de automatización predefinidas |
| **Logic Gate** | Evaluación de reglas de negocio |

## 📁 Estructura del proyecto

```
├── src/
│   ├── main.py              # Entry point
│   ├── config.py            # Configuración global
│   ├── workflow/            # Motor de workflows
│   ├── events/              # Sistema de eventos
│   ├── tools/               # Herramientas de negocio
│   ├── nlp/                 # NLP determinista
│   ├── data/                # Persistencia SQLite
│   ├── license/             # Sistema de licencias
│   ├── web/                 # Web UI (Flask + HTML/CSS/JS)
│   └── utils/               # Utilidades
├── installer/               # Instalador
├── docs/                    # Documentación
└── requirements.txt         # Dependencias
```

## 🔑 Licencias

| Tipo | Precio | Descripción |
|---|---|---|
| **Free** | $0 | Hasta 3 workflows, solo CRM |
| **Individual** | $399 | Ilimitado, todas las herramientas |
| **Revendedor** | $1,499 | Hasta 10 clientes |
| **Empresa** | $2,499 | Ilimitado |

## 🛡️ Seguridad

- Contraseñas hasheadas con bcrypt (cost=12)
- Cookies con httpOnly, secure, sameSite
- License Keys firmadas con HMAC-SHA256
- Parser seguro (sin eval())
- Todo local, zero datos en la nube

## 📦 Build desde código

```bash
# Con PyInstaller
bash installer/build_pyinstaller.sh

# Con Nuitka (alternativo)
bash installer/build_nuitka.sh
```

## 🧪 Tests

```bash
# Ejecutar todos los tests
pytest src/tests/ -v

# Con cobertura
pytest src/tests/ --cov=src --cov-report=term-missing
```

## 📄 Licencia

Propietaria — Pago Único. Ver detalles en la [documentación](docs/MASTERPLAN-WORKFLOW-DETERMINISTA.md).
