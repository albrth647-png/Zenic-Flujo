-- Migración HAT v2.0 (M9) — Reducir Ledger de 7 a 3 tablas
--
-- Ejecutar ANTES de arrancar la aplicación con la nueva versión.
--
-- Pasos:
-- 1. Backup de tablas a eliminar
-- 2. Añadir columnas nuevas a hat_progress
-- 3. Migrar datos de hat_dispatch_registry → hat_progress
-- 4. Eliminar tablas no usadas

-- 1. Backup (renombrar tablas viejas)
ALTER TABLE hat_plan RENAME TO hat_plan_backup_m9;
ALTER TABLE hat_dispatch_registry RENAME TO hat_dispatch_registry_backup_m9;
ALTER TABLE hat_agent_cards RENAME TO hat_agent_cards_backup_m9;
ALTER TABLE hat_sessions RENAME TO hat_sessions_backup_m9;

-- 2. Añadir columnas nuevas a hat_progress (si no existen)
-- Nota: SQLite no soporta "ADD COLUMN IF NOT EXISTS", se hace con try/catch en Python
-- Estos ALTER TABLE pueden fallar si las columnas ya existen — es OK.

ALTER TABLE hat_progress ADD COLUMN intent_hash TEXT;
ALTER TABLE hat_progress ADD COLUMN ttl_expires_at TIMESTAMP;
ALTER TABLE hat_progress ADD COLUMN subscriber_count INTEGER DEFAULT 0;

-- 2b. Renombrar started_at -> created_at para alinear con schema.sql v2.0
-- (solo aplica a DBs existentes creadas con schema v1.0; SQLite >= 3.25.0)
ALTER TABLE hat_progress RENAME COLUMN started_at TO created_at;

-- 3. Migrar datos de hat_dispatch_registry → hat_progress
INSERT INTO hat_progress (user_id, session_id, dispatch_id, domain, status, intent_hash, created_at, completed_at)
SELECT user_id, session_id, intent_hash AS dispatch_id, domain, status, intent_hash, created_at, completed_at
FROM hat_dispatch_registry_backup_m9
WHERE intent_hash NOT IN (SELECT intent_hash FROM hat_progress WHERE intent_hash IS NOT NULL);

-- 4. Crear índices nuevos
CREATE INDEX IF NOT EXISTS idx_progress_hash ON hat_progress(intent_hash);
CREATE INDEX IF NOT EXISTS idx_progress_ttl ON hat_progress(ttl_expires_at);

-- Nota: Las tablas backup se pueden eliminar manualmente después de verificar:
-- DROP TABLE hat_plan_backup_m9;
-- DROP TABLE hat_dispatch_registry_backup_m9;
-- DROP TABLE hat_agent_cards_backup_m9;
-- DROP TABLE hat_sessions_backup_m9;
