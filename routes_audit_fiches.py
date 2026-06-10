"""API routes for audit fiches (PDFs)."""

import logging
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from audit_fiches_manager import AuditFichesManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit-fiches", tags=["audit-fiches"])


@router.get("/list")
async def get_fiches(
    sucursal_id: Optional[str] = Query(None, description="Filter by sucursal ID"),
    fecha_desde: Optional[str] = Query(None, description="From date (ISO format: YYYY-MM-DD)"),
    fecha_hasta: Optional[str] = Query(None, description="To date (ISO format: YYYY-MM-DD)"),
    auditor_nombre: Optional[str] = Query(None, description="Filter by auditor name"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get audit fiches with optional filters.

    Example:
    GET /api/audit-fiches/list?sucursal_id=SC-001&fecha_desde=2026-06-01&fecha_hasta=2026-06-30
    """

    try:
        fiches = await AuditFichesManager.get_fiches(
            sucursal_id=sucursal_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            auditor_nombre=auditor_nombre,
            limit=limit,
            offset=offset,
        )

        return {
            "status": "ok",
            "count": len(fiches),
            "data": fiches,
            "filters": {
                "sucursal_id": sucursal_id,
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "auditor_nombre": auditor_nombre,
            },
        }

    except Exception as e:
        logger.error(f"Error fetching fiches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sucursales")
async def get_sucursales():
    """Get list of sucursales that have audit fiches."""

    try:
        sucursales = await AuditFichesManager.get_sucursales_with_fiches()

        # Extract unique sucursal_ids
        unique_sucursales = []
        seen = set()
        for item in sucursales:
            sucursal_id = item.get("sucursal_id")
            if sucursal_id and sucursal_id not in seen:
                unique_sucursales.append(sucursal_id)
                seen.add(sucursal_id)

        return {
            "status": "ok",
            "count": len(unique_sucursales),
            "data": unique_sucursales,
        }

    except Exception as e:
        logger.error(f"Error fetching sucursales: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ficha_id}")
async def get_ficha_details(ficha_id: str):
    """Get details of specific ficha."""

    try:
        from supabase_manager import SupabaseManager

        db = SupabaseManager()
        response = db.client.table("audit_fiches").select("*").eq("id", ficha_id).single().execute()

        if response.data:
            return {
                "status": "ok",
                "data": response.data,
            }
        else:
            raise HTTPException(status_code=404, detail="Ficha not found")

    except Exception as e:
        logger.error(f"Error fetching ficha details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
