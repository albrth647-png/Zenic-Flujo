# Helm Charts

## Canonical chart (use this)

**Location:** `deploy/helm/zenic-flujo/`

This is the canonical Helm chart with full features: NetworkPolicy, ServiceMonitor, PVC, NOTES.txt.

## Legacy chart (archived)

**Location:** `helm/legacy/zenic-flijo/`

Fix Sprint 4 bug #64: this chart was duplicated with divergent appVersion (3.1.0
vs canonical 1.0.0). Archived to `helm/legacy/` for reference. Do not use in
production — use `deploy/helm/zenic-flujo/` instead.

If you need a feature from the legacy chart not in canonical, port it to
canonical and delete the legacy version.
