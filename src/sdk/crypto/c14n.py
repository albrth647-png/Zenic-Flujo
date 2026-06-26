"""Canonicalization (C14N) para facturación electrónica LATAM.

SAT México (CFDI) requiere XSLT para generar la cadena original.
SEFAZ Brasil (NF-e) requiere C14N 1.1 sobre el nodo infNFe.

Usa lxml (BSD-3) que tiene soporte nativo para canonicalización XML.

Uso:
    from src.sdk.crypto.c14n import canonicalize_cfdi, canonicalize_nfe
    cadena_original = canonicalize_cfdi(xml_bytes, xslt_path)
    canon_nfe = canonicalize_nfe(xml_bytes, reference_id="#NFe")
"""
from __future__ import annotations

import logging
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)


def canonicalize_cfdi(
    xml_bytes: bytes,
    xslt_path: str | Path | None = None,
) -> str:
    """Genera la cadena original de un CFDI usando XSLT SAT.

    SAT publica cadenaoriginal_4_0.xslt para CFDI 4.0.
    Descargar desde: https://www.sat.gob.mx/cs/Satellite?blobcol=urldata...

    Args:
        xml_bytes: XML del CFDI (bytes).
        xslt_path: Path al XSLT de SAT (cadenaoriginal_4_0.xslt).
                   Si None, intenta ruta default.

    Returns:
        Cadena original como string (texto plano, no XML).

    Raises:
        FileNotFoundError: Si el XSLT no existe.
        Exception: Si la transformación falla.
    """
    if xslt_path is None:
        xslt_path = Path.home() / ".zenic-flujo" / "sat" / "cadenaoriginal_4_0.xslt"

    xslt_file = Path(xslt_path)
    if not xslt_file.exists():
        raise FileNotFoundError(
            f"XSLT SAT no encontrado: {xslt_path}. "
            "Descargar cadenaoriginal_4_0.xslt desde sat.gob.mx"
        )

    # Parsear XML y XSLT
    doc = etree.fromstring(xml_bytes)
    xslt_doc = etree.parse(str(xslt_file))
    transform = etree.XSLT(xslt_doc)

    # Aplicar transformación
    result = transform(doc)
    cadena = str(result)

    logger.debug("Cadena original CFDI generada (%d chars)", len(cadena))
    return cadena


def canonicalize_nfe(
    xml_bytes: bytes,
    reference_id: str = "#NFe",
) -> bytes:
    """Canonicaliza XML NF-e usando C14N 1.1 (sin comentarios).

    SEFAZ requiere canonicalización del nodo infNFe para verificar
    la firma XMLDSig.

    Args:
        xml_bytes: XML de la NF-e (bytes).
        reference_id: ID del nodo a canonicalizar (default "#NFe").

    Returns:
        XML canonicalizado como bytes.

    Raises:
        Exception: Si el nodo no se encuentra o la canonicalización falla.
    """
    root = etree.fromstring(xml_bytes)

    # Buscar el nodo por ID
    # lxml usa .find() con expresiones XPath
    ref = reference_id.lstrip("#")
    node = root.find(f".//*[@Id='{ref}']")

    if node is None:
        # Intentar buscar por tag name (infNFe)
        node = root.find(".//infNFe")
        if node is None:
            raise ValueError(f"Nodo con Id='{ref}' no encontrado en el XML")

    # C14N 1.1 sin comentarios
    canon_bytes = etree.tostring(
        node,
        method="c14n",
        exclusive=False,
        with_comments=False,
    )

    logger.debug("NF-e canonicalizada (%d bytes)", len(canon_bytes))
    return canon_bytes


def canonicalize_xml(
    xml_bytes: bytes,
    exclusive: bool = True,
    with_comments: bool = False,
) -> bytes:
    """Canonicalización XML genérica (C14N 1.0).

    Args:
        xml_bytes: XML a canonicalizar (bytes).
        exclusive: Si True, usa C14N exclusivo (quita namespaces no usados).
        with_comments: Si True, incluye comentarios.

    Returns:
        XML canonicalizado como bytes.
    """
    root = etree.fromstring(xml_bytes)
    return etree.tostring(
        root,
        method="c14n",
        exclusive=exclusive,
        with_comments=with_comments,
    )
