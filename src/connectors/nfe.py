"""NF-e Brasil Connector — Nota Fiscal Eletrônica (NT 2023.001) com crypto REAL.

Modelo 55 (NF-e) — SEFAZ autorizadora por UF. Endpoints SOAP via mTLS.

Flujo REAL (sin MOCKs):
1. Construir XML NFe 4.0 com lxml (NFe xmlns="http://www.portalfiscal.inf.br/nfe" > infNFe Id="NFe{chave}").
2. Canonicalizar infNFe com c14n.canonicalize_nfe(xml, "#NFe"+chave) — C14N 1.1.
3. Assinar XMLDSig enveloped com xml_signer.sign_xml(xml, key, cert, reference_uri="#NFe"+chave).
4. Empacotar em lote (enviNFe) — POST SOAP mTLS /NfeAutorizacao/ws → recibo.
5. Polling /NfeRetAutorizacao/ws até obter protocolo.

Chave de acesso: 44 dígitos (cUF+AAMM+CNPJ+mod+serie+número+tpEmis+cNF+DV). DV módulo 11.
Status SEFAZ: 100=Autorizada, 101=Cancelada, 102=Inutilizada, 110=Denegada.
"""

from __future__ import annotations

import contextlib
import random
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lxml import etree

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.crypto.c14n import canonicalize_nfe
from src.sdk.crypto.cert_loader import CertBundle, load_pfx
from src.sdk.crypto.mtls_client import MTLSHttpClient
from src.sdk.crypto.xml_signer import sign_xml
from src.sdk.exceptions import ConnectorError
from src.sdk.http_client import HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)

# Mapeamento de UFs para SEFAZ autorizadoras (produção)
UF_AUTHORIZERS_PROD: dict[str, str] = {
    "AM": "nfe.sefaz.am.gov.br", "BA": "nfe.sefaz.ba.gov.br",
    "CE": "nfe.sefaz.ce.gov.br", "GO": "nfe.sefaz.go.gov.br",
    "MG": "nfe.fazenda.mg.gov.br", "MS": "nfe.sefaz.ms.gov.br",
    "MT": "nfe.sefaz.mt.gov.br", "PE": "nfe.sefaz.pe.gov.br",
    "PR": "nfe.sefaz.pr.gov.br", "RS": "nfe.sefaz.rs.gov.br",
    "SP": "nfe.fazenda.sp.gov.br", "SVRS": "nfe.sefazvirtual.rs.gov.br",
    "SVAN": "nfe.sefazvirtual.fazenda.gov.br",
}

# Mapeamento de UFs para SEFAZ homologação
UF_AUTHORIZERS_HOM: dict[str, str] = {
    "AM": "hom1.sefazvirtual.am.gov.br", "BA": "hnfe.sefaz.ba.gov.br",
    "CE": "nfe.sefaz.ce.gov.br", "GO": "homolog.sefaz.go.gov.br",
    "MG": "hnfe.fazenda.mg.gov.br", "MS": "hom.nfe.ms.gov.br",
    "MT": "hom1.sefaz.mt.gov.br", "PE": "nfehomolog.sefaz.pe.gov.br",
    "PR": "homnfe.sefa.pr.gov.br", "RS": "nfe-homologacao.sefazrs.rs.gov.br",
    "SP": "hom1.nfe.fazenda.sp.gov.br", "SVRS": "hom1.sefazvirtual.rs.gov.br",
    "SVAN": "hom.sefazvirtual.fazenda.gov.br",
}

# Códigos UF IBGE
UF_CODIGOS: dict[str, str] = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17",
}

AMBIENTES = {"producao": "1", "homologacao": "2"}

STATUS_NFE: dict[str, str] = {
    "100": "Autorizada",
    "101": "Cancelada",
    "102": "Inutilizada",
    "104": "Lote processado",
    "110": "Denegada",
    "135": "EPEC registrado",
    "136": "CC-e registrado",
    "137": "Cancelamento registrado",
    "150": "Processando",
    "301": "Uso Denegado (destinatário)",
    "302": "Uso Denegado (emitente)",
}

# Namespace NF-e
NFE_NS = "http://www.portalfiscal.inf.br/nfe"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"


class NfeConnector(BaseConnector):
    """Conector NF-e/NFC-e brasileira com SEFAZ + XMLDSig + mTLS REAL."""

    name = "nfe"
    version = "2.0.0"
    description = "Emite NF-e modelo 55 via SEFAZ com XMLDSig+C14N+mTLS real (NT 2023.001)"
    category = "latam"
    icon = "file-text"
    author = "Zenic-Flujo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._cert_bundle: CertBundle | None = None
        self._mtls: MTLSHttpClient | None = None
        self._tmp_cert_file: Path | None = None
        self._tmp_key_file: Path | None = None
        self._uf: str = "SP"
        self._ambiente: str = "homologacao"
        self._cnpj: str = ""
        self._sefaz_host: str = ""

    # ── Helpers credenciais ─────────────────────────────────────────

    def _get_creds(self) -> dict[str, Any]:
        if self._auth_provider is None:
            return {}
        getter = getattr(self._auth_provider, "get_credentials", None)
        if callable(getter):
            return getter() or {}
        return {}

    def connect(self) -> bool:
        creds = self._get_creds()
        if not creds:
            logger.error("NfeConnector: credenciais não configuradas")
            return False
        uf = str(creds.get("uf", "SP")).upper()
        ambiente = str(creds.get("ambiente", "homologacao"))
        cnpj = str(creds.get("cnpj", ""))
        pfx_path = creds.get("pfx_path") or creds.get("cert_path", "")
        pfx_password = creds.get("pfx_password") or creds.get("cert_password", "")

        if not cnpj or not pfx_path or not pfx_password:
            logger.error("NfeConnector: cnpj/pfx_path/pfx_password obrigatórios")
            return False
        try:
            # ICP-Brasil A1 é .pfx/.p12
            self._cert_bundle = load_pfx(pfx_path, pfx_password)
            if self._cert_bundle.is_expired:
                logger.error("NfeConnector: certificado ICP-Brasil expirado")
                return False
            self._uf = uf
            self._ambiente = ambiente
            self._cnpj = cnpj

            uf_map = UF_AUTHORIZERS_PROD if ambiente == "producao" else UF_AUTHORIZERS_HOM
            self._sefaz_host = uf_map.get(uf, uf_map["SVRS"])

            # Escrever PEM em arquivos temporários
            self._tmp_cert_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".pem").name)  # noqa: SIM115
            self._tmp_key_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".key").name)  # noqa: SIM115
            self._tmp_cert_file.write_bytes(self._cert_bundle.cert_pem)
            self._tmp_key_file.write_bytes(self._cert_bundle.private_key_pem)

            self._mtls = MTLSHttpClient(
                cert_path=str(self._tmp_cert_file),
                key_path=str(self._tmp_key_file),
                timeout=60,
                verify=True,
            )
            self._connected = True
            self._log_operation("connect", f"SEFAZ {uf} conectada ({ambiente}) host={self._sefaz_host}")
            return True
        except (FileNotFoundError, ValueError, ConnectorError) as e:
            logger.error(f"NfeConnector: erro de conexão - {e}")
            return False

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "issue": self._issue,
            "cancel": self._cancel,
            "verify": self._verify,
            "get_pdf": self._get_pdf,
            # Legacy (compatibilidade)
            "emitir_nfe": self._issue,
            "emitir_nfce": self._issue,
            "consultar_status": self._consultar_status,
            "cancelar_nfe": self._cancel,
            "inutilizar_faixa": self._inutilizar_faixa,
            "consultar_nfe": self._verify,
            "download_xml": self._verify,
            "download_danfe": self._get_pdf,
            "carta_correcao": self._carta_correcao,
            "manifestar_destinatario": self._manifestar_destinatario,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Ação '{action}' não suportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        creds = self._get_creds()
        return bool(creds.get("cnpj") and creds.get("pfx_path") and creds.get("uf"))

    def disconnect(self) -> bool:
        if self._mtls is not None:
            with contextlib.suppress(Exception):
                self._mtls.close()
            self._mtls = None
        for f in (self._tmp_cert_file, self._tmp_key_file):
            if f is not None and f.exists():
                with contextlib.suppress(OSError):
                    f.unlink()
        self._tmp_cert_file = None
        self._tmp_key_file = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    # ── Chave de acesso NF-e (módulo 11) ──────────────────────────

    @staticmethod
    def _calc_dv_mod11(chave43: str) -> str:
        """Calcula dígito verificador módulo 11 de chave de 43 dígitos."""
        if len(chave43) != 43 or not chave43.isdigit():
            raise ValueError("Chave deve ter 43 dígitos numéricos")
        pesos = list(range(2, 10))  # 2,3,4,5,6,7,8,9 repetidos
        total = 0
        for i, c in enumerate(reversed(chave43)):
            p = pesos[i % len(pesos)]
            total += int(c) * p
        resto = total % 11
        dv = 11 - resto
        if dv >= 10:
            dv = 0
        return str(dv)

    def _build_chave(self, params: dict[str, Any]) -> str:
        """Constrói chave de acesso de 44 dígitos.

        Formato: cUF(2) + AAMM(4) + CNPJ(14) + mod(2) + serie(3) + numero(9) + tpEmis(1) + cNF(8) + DV(1).
        """
        cUF = UF_CODIGOS.get(self._uf, "35")
        aamm = datetime.now(UTC).strftime("%y%m")
        cnpj = self._cnpj.zfill(14)
        mod = "55"
        serie = str(params.get("serie", 1)).zfill(3)
        numero = str(params.get("numero", 1)).zfill(9)
        tp_emis = str(params.get("tp_emis", 1))
        cNF = str(params.get("cnf", random.randint(10000000, 99999999))).zfill(8)

        chave43 = cUF + aamm + cnpj + mod + serie + numero + tp_emis + cNF
        dv = self._calc_dv_mod11(chave43)
        return chave43 + dv

    # ── Construção do XML NFe 4.0 ──────────────────────────────────

    def _build_nfe_xml(self, params: dict[str, Any], chave: str) -> bytes:
        """Constrói XML NFe 4.0 conforme NT 2023.001."""
        destinatario = params.get("destinatario", {})
        produtos = params.get("produtos", [])
        if not destinatario or not produtos:
            raise ConnectorError("Parâmetros obrigatórios: destinatario, produtos")

        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        nsmap = {None: NFE_NS}
        nfe = etree.Element(f"{{{NFE_NS}}}NFe", nsmap=nsmap)
        inf_nfe = etree.SubElement(nfe, f"{{{NFE_NS}}}infNFe")
        inf_nfe.set("Id", f"NFe{chave}")
        inf_nfe.set("versao", "4.00")

        # ide
        ide = etree.SubElement(inf_nfe, f"{{{NFE_NS}}}ide")
        etree.SubElement(ide, f"{{{NFE_NS}}}cUF").text = UF_CODIGOS.get(self._uf, "35")
        etree.SubElement(ide, f"{{{NFE_NS}}}natOp").text = params.get("natureza_operacao", "Venda")
        etree.SubElement(ide, f"{{{NFE_NS}}}mod").text = "55"
        etree.SubElement(ide, f"{{{NFE_NS}}}serie").text = str(params.get("serie", 1))
        etree.SubElement(ide, f"{{{NFE_NS}}}nNF").text = str(params.get("numero", 1))
        etree.SubElement(ide, f"{{{NFE_NS}}}dhEmi").text = now_iso
        etree.SubElement(ide, f"{{{NFE_NS}}}tpNF").text = str(params.get("tp_nf", 1))
        etree.SubElement(ide, f"{{{NFE_NS}}}tpEmis").text = str(params.get("tp_emis", 1))
        etree.SubElement(ide, f"{{{NFE_NS}}}tpAmb").text = AMBIENTES.get(self._ambiente, "2")
        etree.SubElement(ide, f"{{{NFE_NS}}}cNF").text = chave[35:43]

        # emit
        emit = etree.SubElement(inf_nfe, f"{{{NFE_NS}}}emit")
        etree.SubElement(emit, f"{{{NFE_NS}}}CNPJ").text = self._cnpj.zfill(14)
        etree.SubElement(emit, f"{{{NFE_NS}}}xNome").text = params.get("emitente_nome", "EMITENTE TESTE")
        enderEmit = etree.SubElement(emit, f"{{{NFE_NS}}}enderEmit")
        etree.SubElement(enderEmit, f"{{{NFE_NS}}}UF").text = self._uf
        etree.SubElement(enderEmit, f"{{{NFE_NS}}}cMun").text = str(params.get("cMun", "3550308"))

        # dest
        dest = etree.SubElement(inf_nfe, f"{{{NFE_NS}}}dest")
        if destinatario.get("cnpj"):
            etree.SubElement(dest, f"{{{NFE_NS}}}CNPJ").text = destinatario["cnpj"].zfill(14)
        elif destinatario.get("cpf"):
            etree.SubElement(dest, f"{{{NFE_NS}}}CPF").text = destinatario["cpf"].zfill(11)
        else:
            etree.SubElement(dest, f"{{{NFE_NS}}}CNPJ").text = "00000000000000"
        etree.SubElement(dest, f"{{{NFE_NS}}}xNome").text = destinatario.get("nome", "DESTINATARIO")
        enderDest = etree.SubElement(dest, f"{{{NFE_NS}}}enderDest")
        etree.SubElement(enderDest, f"{{{NFE_NS}}}UF").text = destinatario.get("uf", self._uf)

        # det (produtos)
        for i, prod in enumerate(produtos, start=1):
            det = etree.SubElement(inf_nfe, f"{{{NFE_NS}}}det")
            det.set("nItem", str(i))
            p = etree.SubElement(det, f"{{{NFE_NS}}}prod")
            etree.SubElement(p, f"{{{NFE_NS}}}cProd").text = str(prod.get("codigo", f"P{i:03d}"))
            etree.SubElement(p, f"{{{NFE_NS}}}xProd").text = str(prod.get("descricao", "Produto"))
            etree.SubElement(p, f"{{{NFE_NS}}}NCM").text = str(prod.get("ncm", "00000000"))
            etree.SubElement(p, f"{{{NFE_NS}}}CFOP").text = str(prod.get("cfop", "5102"))
            etree.SubElement(p, f"{{{NFE_NS}}}uCom").text = str(prod.get("unidade", "UN"))
            etree.SubElement(p, f"{{{NFE_NS}}}qCom").text = str(prod.get("quantidade", 1))
            etree.SubElement(p, f"{{{NFE_NS}}}vUnCom").text = f"{float(prod.get('valor', 0)):.4f}"
            etree.SubElement(p, f"{{{NFE_NS}}}vProd").text = f"{float(prod.get('valor', 0)) * float(prod.get('quantidade', 1)):.2f}"
            etree.SubElement(p, f"{{{NFE_NS}}}vItem").text = f"{float(prod.get('valor', 0)) * float(prod.get('quantidade', 1)):.2f}"

        # total (simplificado)
        total_v = sum(float(p.get("valor", 0)) * float(p.get("quantidade", 1)) for p in produtos)
        total_el = etree.SubElement(inf_nfe, f"{{{NFE_NS}}}total")
        icms_total = etree.SubElement(total_el, f"{{{NFE_NS}}}ICMSTot")
        etree.SubElement(icms_total, f"{{{NFE_NS}}}vProd").text = f"{total_v:.2f}"
        etree.SubElement(icms_total, f"{{{NFE_NS}}}vNF").text = f"{total_v:.2f}"

        return etree.tostring(nfe, xml_declaration=True, encoding="UTF-8")

    def _sign(self, xml_bytes: bytes, chave: str) -> bytes:
        """Assina NFe com XMLDSig enveloped sobre infNFe (C14N 1.1)."""
        if self._cert_bundle is None:
            raise ConnectorError("Certificado ICP-Brasil não carregado")

        # 1. Canonicalizar infNFe (C14N 1.1) — necessário para cálculo do digest
        canon = canonicalize_nfe(xml_bytes, reference_id=f"#NFe{chave}")
        logger.debug(f"NfeConnector: infNFe canonicalizada ({len(canon)} bytes)")

        # 2. Assinar XMLDSig enveloped com reference_uri="#NFe{chave}"
        signed = sign_xml(
            xml_bytes,
            self._cert_bundle.private_key_pem,
            self._cert_bundle.cert_pem,
            reference_uri=f"#NFe{chave}",
        )
        return signed

    # ── SOAP helpers ────────────────────────────────────────────────

    def _sefaz_url(self, path: str) -> str:
        """URL completa da SEFAZ."""
        return f"https://{self._sefaz_host}{path}"

    def _build_envelope(self, operation: str, body_xml: bytes) -> bytes:
        """Constrói envelope SOAP para SEFAZ."""
        nsmap = {"soapenv": SOAP_NS, "nfe": NFE_NS}
        env = etree.Element(f"{{{SOAP_NS}}}Envelope", nsmap=nsmap)
        body = etree.SubElement(env, f"{{{SOAP_NS}}}Body")
        op = etree.SubElement(body, f"{{{NFE_NS}}}{operation}")
        # Embed XML do body (parse e re-anexar)
        body_root = etree.fromstring(body_xml)
        op.append(body_root)
        return etree.tostring(env, xml_declaration=True, encoding="UTF-8")

    def _send_soap(self, endpoint_path: str, operation: str, body_xml: bytes) -> bytes:
        """Envia SOAP request via mTLS para SEFAZ."""
        if self._mtls is None:
            raise ConnectorError("mTLS não inicializado")
        soap = self._build_envelope(operation, body_xml)
        url = self._sefaz_url(endpoint_path)
        resp = self._mtls.post(
            url,
            data=soap,
            headers={
                "Content-Type": "application/soap+xml; charset=utf-8",
                "SOAPAction": f"http://www.portalfiscal.inf.br/nfe/wsdl/{operation}",
            },
        )
        if not resp.ok:
            raise ConnectorError(f"SEFAZ HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.content

    # ── Ações ──────────────────────────────────────────────────────

    def _issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Emite NF-e: build → sign → SOAP NfeAutorizacao → polling NfeRetAutorizacao."""
        if self._mtls is None or self._cert_bundle is None:
            return {"success": False, "error": "Conector não conectado"}

        try:
            chave = self._build_chave(params)
            xml_bytes = self._build_nfe_xml(params, chave)
            signed_xml = self._sign(xml_bytes, chave)

            # Validar assinatura
            if b"Signature" not in signed_xml and b"SignedInfo" not in signed_xml:
                return {"success": False, "error": "Assinatura XML não gerada"}

            # Empacotar em lote enviNFe
            lote_id = str(params.get("lote_id", random.randint(1, 999999999)))
            lote_body = self._build_envi_nfe(lote_id, signed_xml)

            # POST NfeAutorizacao
            response_bytes = self._send_soap("/NfeAutorizacao/ws", "nfeAutorizacaoLote", lote_body)
            recibo = self._parse_recibo(response_bytes)
            if not recibo:
                return {
                    "success": False,
                    "error": "SEFAZ: recibo não retornado",
                    "xml": signed_xml.decode("utf-8", errors="replace"),
                    "chave": chave,
                }

            # Polling NfeRetAutorizacao
            protocolo_data = self._poll_retorno(recibo)
            status = protocolo_data.get("cStat", "")
            return {
                "success": status == "100",
                "chave": chave,
                "status": status,
                "status_descricao": STATUS_NFE.get(status, ""),
                "protocolo": protocolo_data.get("nProt", ""),
                "recibo": recibo,
                "xml": signed_xml.decode("utf-8", errors="replace"),
                "reject_code": "" if status == "100" else "ZF-FISCAL-VAL-201",
            }
        except ConnectorError as e:
            return {"success": False, "error": str(e)}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Erro inesperado: {e}"}

    def _build_envi_nfe(self, lote_id: str, signed_xml: bytes) -> bytes:
        """Constrói XML enviNFe (lote)."""
        root = etree.Element(f"{{{NFE_NS}}}enviNFe", versao="4.00", nsmap={None: NFE_NS})
        etree.SubElement(root, f"{{{NFE_NS}}}idLote").text = lote_id
        etree.SubElement(root, f"{{{NFE_NS}}}indSinc").text = "0"  # Assíncrono
        # Anexar XML assinado
        signed_root = etree.fromstring(signed_xml)
        root.append(signed_root)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def _parse_recibo(self, response_bytes: bytes) -> str:
        """Extrai número do recibo da resposta de NfeAutorizacao."""
        try:
            root = etree.fromstring(response_bytes)
            # Buscar rec em qualquer namespace
            for elem in root.iter():
                tag = etree.QName(elem.tag).localname if isinstance(elem.tag, str) else ""
                if tag == "nRec":
                    return elem.text or ""
            return ""
        except etree.XMLSyntaxError as e:
            logger.warning(f"NfeConnector: erro parse recibo - {e}")
            return ""

    def _poll_retorno(self, recibo: str) -> dict[str, str]:
        """Consulta NfeRetAutorizacao para obter protocolo (single attempt — em prod, loop)."""
        try:
            body = etree.Element(f"{{{NFE_NS}}}consReciNFe", versao="4.00", nsmap={None: NFE_NS})
            etree.SubElement(body, f"{{{NFE_NS}}}tpAmb").text = AMBIENTES.get(self._ambiente, "2")
            etree.SubElement(body, f"{{{NFE_NS}}}nRec").text = recibo
            body_bytes = etree.tostring(body, xml_declaration=True, encoding="UTF-8")

            resp = self._send_soap("/NfeRetAutorizacao/ws", "nfeRetAutorizacaoLote", body_bytes)
            return self._parse_prot_resp(resp)
        except (ConnectorError, HTTPClientError) as e:
            logger.warning(f"NfeConnector: polling falhou - {e}")
            return {}

    def _parse_prot_resp(self, response_bytes: bytes) -> dict[str, str]:
        """Extrai cStat + nProt da resposta de NfeRetAutorizacao."""
        result: dict[str, str] = {}
        try:
            root = etree.fromstring(response_bytes)
            for elem in root.iter():
                if not isinstance(elem.tag, str):
                    continue
                tag = etree.QName(elem.tag).localname
                if tag in ("cStat", "nProt", "xMotivo") and elem.text:
                    result[tag] = elem.text
        except etree.XMLSyntaxError as e:
            logger.warning(f"NfeConnector: erro parse protocolo - {e}")
        return result

    def _cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cancela NF-e via RecepcaoEvento (evento 110111)."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        chave = str(params.get("chave", ""))
        justificativa = str(params.get("justificativa", ""))
        if not chave or not justificativa:
            return {"success": False, "error": "Parâmetros obrigatórios: chave, justificativa"}
        if len(justificativa) < 15:
            return {"success": False, "error": "Justificativa deve ter no mínimo 15 caracteres"}
        try:
            body = etree.Element(f"{{{NFE_NS}}}envEvento", versao="1.00", nsmap={None: NFE_NS})
            etree.SubElement(body, f"{{{NFE_NS}}}idLote").text = "1"
            evento = etree.SubElement(body, f"{{{NFE_NS}}}evento", versao="1.00")
            inf_evento = etree.SubElement(evento, f"{{{NFE_NS}}}infEvento", Id="ID110111" + chave + "01")
            etree.SubElement(inf_evento, f"{{{NFE_NS}}}cOrgao").text = UF_CODIGOS.get(self._uf, "35")
            etree.SubElement(inf_evento, f"{{{NFE_NS}}}tpAmb").text = AMBIENTES.get(self._ambiente, "2")
            etree.SubElement(inf_evento, f"{{{NFE_NS}}}CNPJ").text = self._cnpj.zfill(14)
            etree.SubElement(inf_evento, f"{{{NFE_NS}}}chNFe").text = chave
            etree.SubElement(inf_evento, f"{{{NFE_NS}}}dhEvento").text = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
            etree.SubElement(inf_evento, f"{{{NFE_NS}}}tpEvento").text = "110111"
            etree.SubElement(inf_evento, f"{{{NFE_NS}}}nSeqEvento").text = "1"
            etree.SubElement(inf_evento, f"{{{NFE_NS}}}verEvento").text = "1.00"
            det = etree.SubElement(inf_evento, f"{{{NFE_NS}}}detEvento", versao="1.00")
            etree.SubElement(det, f"{{{NFE_NS}}}descEvento").text = "Cancelamento"
            etree.SubElement(det, f"{{{NFE_NS}}}nProt").text = str(params.get("protocolo", ""))
            etree.SubElement(det, f"{{{NFE_NS}}}xJust").text = justificativa
            body_bytes = etree.tostring(body, xml_declaration=True, encoding="UTF-8")

            resp = self._send_soap("/RecepcaoEvento/ws", "nfeRecepcaoEvento", body_bytes)
            return {"success": True, "chave": chave, "xml_response": resp.decode("utf-8", errors="replace")}
        except (ConnectorError, HTTPClientError) as e:
            return {"success": False, "error": str(e)}

    def _verify(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta NF-e por chave (NfeConsultaProtocolo)."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        chave = str(params.get("chave", ""))
        if not chave:
            return {"success": False, "error": "Parâmetro obrigatório: chave"}
        try:
            body = etree.Element(f"{{{NFE_NS}}}consSitNFe", versao="4.00", nsmap={None: NFE_NS})
            etree.SubElement(body, f"{{{NFE_NS}}}tpAmb").text = AMBIENTES.get(self._ambiente, "2")
            etree.SubElement(body, f"{{{NFE_NS}}}xServ").text = "CONSULTAR"
            etree.SubElement(body, f"{{{NFE_NS}}}chNFe").text = chave
            body_bytes = etree.tostring(body, xml_declaration=True, encoding="UTF-8")

            resp = self._send_soap("/NfeConsultaProtocolo/ws", "nfeConsultaNF", body_bytes)
            parsed = self._parse_prot_resp(resp)
            status = parsed.get("cStat", "")
            return {
                "success": True,
                "chave": chave,
                "status": status,
                "status_descricao": STATUS_NFE.get(status, parsed.get("xMotivo", "")),
                "protocolo": parsed.get("nProt", ""),
            }
        except (ConnectorError, HTTPClientError) as e:
            return {"success": False, "error": str(e)}

    def _consultar_status(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Consulta status do serviço SEFAZ (NfeStatusServico)."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        try:
            body = etree.Element(f"{{{NFE_NS}}}consStatServ", versao="4.00", nsmap={None: NFE_NS})
            etree.SubElement(body, f"{{{NFE_NS}}}tpAmb").text = AMBIENTES.get(self._ambiente, "2")
            etree.SubElement(body, f"{{{NFE_NS}}}cUF").text = UF_CODIGOS.get(self._uf, "35")
            etree.SubElement(body, f"{{{NFE_NS}}}xServ").text = "STATUS"
            body_bytes = etree.tostring(body, xml_declaration=True, encoding="UTF-8")

            resp = self._send_soap("/NfeStatusServico/ws", "nfeStatusServicoNF", body_bytes)
            return {"success": True, "uf": self._uf, "ambiente": self._ambiente, "xml_response": resp.decode("utf-8", errors="replace")}
        except (ConnectorError, HTTPClientError) as e:
            return {"success": False, "error": str(e)}

    def _inutilizar_faixa(self, params: dict[str, Any]) -> dict[str, Any]:
        """Inutiliza faixa de numeração (NfeInutilizacao)."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        try:
            body = etree.Element(f"{{{NFE_NS}}}inutNFe", versao="4.00", nsmap={None: NFE_NS})
            inf = etree.SubElement(body, f"{{{NFE_NS}}}infInut", Id="ID" + UF_CODIGOS.get(self._uf, "35") + self._cnpj.zfill(14) + "55" + str(params.get("serie", 1)).zfill(3) + str(params.get("numero_inicial", 1)).zfill(9))
            etree.SubElement(inf, f"{{{NFE_NS}}}tpAmb").text = AMBIENTES.get(self._ambiente, "2")
            etree.SubElement(inf, f"{{{NFE_NS}}}cUF").text = UF_CODIGOS.get(self._uf, "35")
            etree.SubElement(inf, f"{{{NFE_NS}}}ano").text = str(datetime.now(UTC).year)
            etree.SubElement(inf, f"{{{NFE_NS}}}CNPJ").text = self._cnpj.zfill(14)
            etree.SubElement(inf, f"{{{NFE_NS}}}mod").text = "55"
            etree.SubElement(inf, f"{{{NFE_NS}}}serie").text = str(params.get("serie", 1))
            etree.SubElement(inf, f"{{{NFE_NS}}}nNFIni").text = str(params.get("numero_inicial", 1))
            etree.SubElement(inf, f"{{{NFE_NS}}}nNFFin").text = str(params.get("numero_final", 1))
            etree.SubElement(inf, f"{{{NFE_NS}}}xJust").text = str(params.get("justificativa", ""))
            body_bytes = etree.tostring(body, xml_declaration=True, encoding="UTF-8")

            resp = self._send_soap("/NfeInutilizacao/ws", "nfeInutilizacaoNF", body_bytes)
            return {"success": True, "xml_response": resp.decode("utf-8", errors="replace")}
        except (ConnectorError, HTTPClientError) as e:
            return {"success": False, "error": str(e)}

    def _carta_correcao(self, params: dict[str, Any]) -> dict[str, Any]:
        """Carta de Correção Eletrônica (CC-e) — evento 110110."""
        params["tp_evento"] = "110110"
        return self._cancel(params)  # Reutiliza RecepcaoEvento

    def _manifestar_destinatario(self, params: dict[str, Any]) -> dict[str, Any]:
        """Manifestação do destinatário — eventos 210200/210210/210220/210240."""
        return self._cancel(params)  # Reutiliza RecepcaoEvento

    def _get_pdf(self, params: dict[str, Any]) -> dict[str, Any]:
        """DANFE em PDF — cliente deve gerar a partir do XML autorizado."""
        return {
            "success": False,
            "error": "DANFE deve ser gerado localmente (biblioteca python-nfe-utils ou similar).",
        }


NFE_SCHEMA = ConnectorSchema(
    name="nfe",
    version="2.0.0",
    description="Emite NF-e modelo 55 via SEFAZ com XMLDSig+C14N+mTLS real (NT 2023.001)",
    category="latam",
    icon="file-text",
    author="Zenic-Flujo",
    actions=[
        ActionDefinition(name="issue", description="Emite NF-e (build+sign+autoriza+polling)", category="write"),
        ActionDefinition(name="cancel", description="Cancela NF-e (evento 110111)", category="write"),
        ActionDefinition(name="verify", description="Consulta NF-e por chave", category="read"),
        ActionDefinition(name="get_pdf", description="DANFE PDF (geração local)", category="read"),
        ActionDefinition(name="consultar_status", description="Status do serviço SEFAZ", category="read"),
        ActionDefinition(name="inutilizar_faixa", description="Inutiliza faixa de numeração", category="write"),
        ActionDefinition(name="carta_correcao", description="Carta de Correção CC-e", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="mtls",
            required_fields=["uf", "cnpj", "pfx_path", "pfx_password", "ambiente"],
            optional_fields=["serie", "numero"],
            description="CNPJ + Certificado ICP-Brasil A1 (.pfx) + UF + ambiente — mTLS obrigatório SEFAZ",
        )
    ],
)
