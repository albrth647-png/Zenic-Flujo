"""
BPMN API Routes — REST endpoints for BPMN process management.

Provides HTTP API for:
- BPMN XML import/export
- BPMN process validation
- BPMN to workflow conversion
- BPMN process listing and management

# Audience: External
# Purpose: Import/export/validate procesos BPMN. Paralelo a Flask /api/workflows/* para integraciones BPMN externas.
"""


from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api_v2.dependencies import require_permission
from src.bpmn import BPMNExporter, BPMNParser, BPMNProcess, BPMNToWorkflowConverter

router = APIRouter(prefix="/api/v2/bpmn", tags=["bpmn"])

# In-memory process store (production would use database)
_processes: dict[str, BPMNProcess] = {}


@router.post("/import", summary="Import a BPMN 2.0 XML process")
async def import_bpmn(
    xml_content: str,
    validate: bool = Query(True, description="Validate after import"),
    _: dict[str, Any] = Depends(require_permission("bpmn", "create")),
) -> dict[str, Any]:
    """Import a BPMN 2.0 XML process definition."""
    parser = BPMNParser()
    try:
        process = parser.parse(xml_content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid BPMN XML: {exc}") from exc

    errors = []
    if validate:
        errors = process.validate()
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "BPMN validation failed", "errors": errors},
            )

    _processes[process.process_id] = process
    return {
        "process_id": process.process_id,
        "name": process.name,
        "elements": len(process.elements),
        "flows": len(process.flows),
        "validation_errors": errors,
    }


@router.post("/export/{process_id}", summary="Export a BPMN process as XML")
async def export_bpmn(
    process_id: str,
    _: dict[str, Any] = Depends(require_permission("bpmn", "read")),
) -> dict[str, Any]:
    """Export a BPMN process as BPMN 2.0 XML."""
    process = _processes.get(process_id)
    if process is None:
        raise HTTPException(status_code=404, detail=f"Process not found: {process_id}")

    exporter = BPMNExporter()
    xml_string = exporter.export(process)
    return {"process_id": process_id, "bpmn_xml": xml_string}


@router.post("/convert/{process_id}", summary="Convert BPMN to workflow")
async def convert_bpmn_to_workflow(
    process_id: str,
    _: dict[str, Any] = Depends(require_permission("bpmn", "read")),
) -> dict[str, Any]:
    """Convert a BPMN process to a Zenic-Flijo workflow definition."""
    process = _processes.get(process_id)
    if process is None:
        raise HTTPException(status_code=404, detail=f"Process not found: {process_id}")

    converter = BPMNToWorkflowConverter()
    workflow_def = converter.convert(process)
    return workflow_def


@router.post("/validate", summary="Validate a BPMN XML")
async def validate_bpmn(
    xml_content: str,
    _: dict[str, Any] = Depends(require_permission("bpmn", "read")),
) -> dict[str, Any]:
    """Validate a BPMN 2.0 XML without importing."""
    parser = BPMNParser()
    try:
        process = parser.parse(xml_content)
    except ValueError as exc:
        return {"valid": False, "errors": [str(exc)]}

    errors = process.validate()
    return {"valid": len(errors) == 0, "errors": errors}


@router.get("/processes", summary="List BPMN processes")
async def list_processes(
    _: dict[str, Any] = Depends(require_permission("bpmn", "read")),
) -> dict[str, Any]:
    """List all imported BPMN processes."""
    processes = []
    for process in _processes.values():
        processes.append({
            "process_id": process.process_id,
            "name": process.name,
            "elements": len(process.elements),
            "flows": len(process.flows),
            "start_events": len(process.get_start_events()),
            "end_events": len(process.get_end_events()),
            "tasks": len(process.get_tasks()),
            "gateways": len(process.get_gateways()),
        })
    return {"processes": processes, "count": len(processes)}


@router.get("/processes/{process_id}", summary="Get BPMN process details")
async def get_process(
    process_id: str,
    _: dict[str, Any] = Depends(require_permission("bpmn", "read")),
) -> dict[str, Any]:
    """Get details of a specific BPMN process."""
    process = _processes.get(process_id)
    if process is None:
        raise HTTPException(status_code=404, detail=f"Process not found: {process_id}")

    return {
        "process_id": process.process_id,
        "name": process.name,
        "is_executable": process.is_executable,
        "documentation": process.documentation,
        "version": process.version,
        "elements": {
            eid: {
                "name": e.name,
                "type": e.element_type.value,
                "incoming": e.incoming,
                "outgoing": e.outgoing,
            }
            for eid, e in process.elements.items()
        },
        "flows": {
            fid: {
                "name": f.name,
                "source": f.source_ref,
                "target": f.target_ref,
                "condition": f.condition_expression,
            }
            for fid, f in process.flows.items()
        },
        "validation": process.validate(),
    }


@router.delete("/processes/{process_id}", summary="Delete a BPMN process")
async def delete_process(
    process_id: str,
    _: dict[str, Any] = Depends(require_permission("bpmn", "delete")),
) -> dict[str, Any]:
    """Delete an imported BPMN process."""
    if process_id not in _processes:
        raise HTTPException(status_code=404, detail=f"Process not found: {process_id}")
    del _processes[process_id]
    return {"status": "deleted", "process_id": process_id}
