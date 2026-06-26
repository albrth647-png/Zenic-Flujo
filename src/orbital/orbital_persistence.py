"""Persistencia de OrbitalResult con hash chain + firma Ed25519.

Foso 1 — Compliance Reproducible Banca LATAM.

Cada OrbitalResult se persiste con:
1. SHA-256(canonical_json(result.to_dict())) → result_hash
2. Ed25519(result_hash, tenant_key) → result_signature
3. result_hash del tick anterior → previous_hash (cadena Merkle-style)

Esto permite verificar:
- Integridad: re-calcular el hash y comparar
- Autenticidad: verificar la firma con la pública del tenant
- Orden: recalcular la cadena y detectar reordenamiento/inserción

Para reguladores (SBS, CNBV, BACEN, SFC, CMF): un ReproducibilityReporter
genera PDFs firmados con todas las verificaciones, con la prueba matemática
de convergencia del COD (Brouwer + Lyapunov + FEP + Conley + Haken).
"""
from __future__ import annotations

from typing import Any

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.core.security.encryption import EncryptionService
from src.orbital.canonical_serializer import (
    canonical_json,
    sha256_hex,
)
from src.orbital.models import OrbitalResult

logger = setup_logging(__name__)


class OrbitalPersistence:
    """Persiste OrbitalResult con garantías de reproducibilidad criptográfica.

    No toca el motor ORBITAL: solo lee el OrbitalResult y lo persiste con
    hash + firma + encadenamiento al tick anterior del mismo workflow_execution.
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        encryption: EncryptionService | None = None,
    ):
        self._db = db or DatabaseManager()
        self._enc = encryption or EncryptionService()

    def save_orbital_result(
        self,
        result: OrbitalResult,
        workflow_execution_id: int,
        tenant_id: str = "default",
        previous_hash: str = "",
    ) -> dict[str, Any]:
        """Persiste un OrbitalResult con hash + firma + encadenamiento.

        Args:
            result: OrbitalResult a persistir (debe tener input_fingerprint ya calculado).
            workflow_execution_id: FK a workflow_executions.id.
            tenant_id: ID del tenant que firma.
            previous_hash: result_hash del tick anterior (vacío si es el primer tick).

        Returns:
            Dict con {orbital_execution_id, result_hash, result_signature, previous_hash}.
        """
        # 1. Serializar canónicamente (sin result_hash/signature — auto-referenciales)
        result.previous_hash = previous_hash
        result.workflow_execution_id = workflow_execution_id
        payload = canonical_json(result.to_dict())

        # 2. Calcular hash
        result_hash = sha256_hex(payload)
        result.result_hash = result_hash

        # 3. Firmar con Ed25519 del tenant
        signature = ""
        try:
            signature = self._enc.sign_payload(payload, tenant_id=tenant_id)
            result.result_signature = signature
        except Exception as e:
            logger.warning(f"OrbitalPersistence: no se pudo firmar (tenant={tenant_id}): {e}")

        # 4. Serializar payloads auxiliares (COD, RCC, TOR) para replay
        cod_payload = canonical_json([c.to_dict() for c in result.cod_results]).decode("utf-8")
        rcc_payload = canonical_json([r.to_dict() for r in result.rcc_results]).decode("utf-8")
        tor_payload = canonical_json([t.to_dict() for t in result.tor_results]).decode("utf-8")

        # 5. Persistir en orbital_executions
        cursor = self._db.execute(
            """
            INSERT INTO orbital_executions
                (tick, total_variables, total_cycles, total_tor_pairs,
                 resonant_cycles, converged_cycles, final_state, duration_ms,
                 workflow_execution_id, input_fingerprint, result_hash,
                 result_signature, previous_hash, cod_payload, rcc_payload,
                 tor_payload, tenant_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.tick,
                len(result.variables),
                len(result.cod_results),
                len(result.tor_results),
                sum(1 for r in result.rcc_results if r.is_resonant),
                sum(1 for c in result.cod_results if c.converged),
                canonical_json(result.to_dict()).decode("utf-8"),
                result.duration_ms,
                workflow_execution_id,
                result.input_fingerprint,
                result_hash,
                signature,
                previous_hash,
                cod_payload,
                rcc_payload,
                tor_payload,
                tenant_id,
            ),
        )
        self._db.commit()
        orbital_exec_id = cursor.lastrowid

        logger.info(
            f"OrbitalResult persistido: id={orbital_exec_id} hash={result_hash[:16]}… "
            f"signed={'yes' if signature else 'no'} prev={previous_hash[:16]}…"
        )

        return {
            "orbital_execution_id": orbital_exec_id,
            "result_hash": result_hash,
            "result_signature": signature,
            "previous_hash": previous_hash,
        }

    def save_step_snapshot(
        self,
        workflow_execution_id: int,
        step_id: int,
        orbital_theta: float,
        orbital_tension: float,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        tenant_id: str = "default",
    ) -> None:
        """Persiste snapshot de un step para replay step-by-step.

        Args:
            workflow_execution_id: FK a workflow_executions.id.
            step_id: ID del step dentro del workflow.
            orbital_theta: Theta promedio de las variables orbitales del step.
            orbital_tension: Tensión promedio.
            input_data: Input que recibió el step.
            output_data: Output que produjo el step.
            tenant_id: Tenant que firma el snapshot.
        """
        input_hash = sha256_hex(canonical_json(input_data))
        output_hash = sha256_hex(canonical_json(output_data))
        payload = canonical_json(
            {
                "exec_id": workflow_execution_id,
                "step_id": step_id,
                "theta": orbital_theta,
                "tension": orbital_tension,
                "input_hash": input_hash,
                "output_hash": output_hash,
            }
        )
        signature = ""
        try:
            signature = self._enc.sign_payload(payload, tenant_id=tenant_id)
        except Exception as e:
            logger.warning(f"OrbitalPersistence: no se pudo firmar step snapshot: {e}")

        self._db.execute(
            """
            INSERT INTO orbital_step_snapshots
                (execution_id, step_id, orbital_theta, orbital_tension,
                 input_hash, output_hash, step_signature)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_execution_id,
                step_id,
                orbital_theta,
                orbital_tension,
                input_hash,
                output_hash,
                signature,
            ),
        )
        self._db.commit()

    def get_last_hash_for_execution(self, workflow_execution_id: int) -> str:
        """Obtiene el result_hash del último tick del workflow_execution.

        Args:
            workflow_execution_id: FK a workflow_executions.id.

        Returns:
            result_hash del último tick, o "" si no hay ticks previos.
        """
        row = self._db.fetchone(
            """
            SELECT result_hash FROM orbital_executions
            WHERE workflow_execution_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (workflow_execution_id,),
        )
        return row["result_hash"] if row else ""

    def load_orbital_execution(self, workflow_execution_id: int) -> dict[str, Any] | None:
        """Carga la última orbital_execution de un workflow_execution.

        Args:
            workflow_execution_id: FK a workflow_executions.id.

        Returns:
            Dict con todos los campos de orbital_executions, o None si no existe.
        """
        return self._db.fetchone(
            """
            SELECT * FROM orbital_executions
            WHERE workflow_execution_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (workflow_execution_id,),
        )

    def verify_orbital_execution(self, workflow_execution_id: int) -> dict[str, Any]:
        """Verifica integridad y autenticidad de la última orbital_execution.

        Re-calcula el hash y verifica la firma Ed25519.

        Returns:
            Dict con {valid, hash_matches, signature_valid, expected_hash, stored_hash}.
        """
        orbital_exec = self.load_orbital_execution(workflow_execution_id)
        if not orbital_exec:
            return {
                "valid": False,
                "error": "orbital_execution no encontrada",
            }

        # Recalcular hash sobre el final_state (que es canonical_json del to_dict)
        final_state_bytes = orbital_exec["final_state"].encode("utf-8")
        recomputed_hash = sha256_hex(final_state_bytes)
        stored_hash = orbital_exec["result_hash"]

        hash_matches = recomputed_hash == stored_hash

        # Verificar firma Ed25519
        signature_valid = False
        if orbital_exec["result_signature"]:
            tenant_id = orbital_exec.get("tenant_id") or "default"
            signature_valid = self._enc.verify_signature(
                final_state_bytes,
                orbital_exec["result_signature"],
                tenant_id=tenant_id,
            )

        return {
            "valid": hash_matches and signature_valid,
            "hash_matches": hash_matches,
            "signature_valid": signature_valid,
            "expected_hash": recomputed_hash,
            "stored_hash": stored_hash,
        }
