"""
XML Processor — Parseo y generación de XML.
Sprint 5.6 del Roadmap Competitivo.
"""

from __future__ import annotations

from src.core.logging import setup_logging
from typing import Any

logger = setup_logging(__name__)


class XMLProcessor:
    """
    Procesa XML: parsea a dict y genera XML desde dict.

    Usa xmltodict si está disponible, fallback a parseo manual básico.
    """

    @staticmethod
    def parse(xml_string: str) -> dict[str, Any]:
        try:
            import xmltodict
            result = xmltodict.parse(xml_string)
            return {"parsed": result, "format": "xml", "parser": "xmltodict"}
        except ImportError:
            logger.warning("xmltodict no instalado, usando parseo básico")
            return XMLProcessor._basic_parse(xml_string)
        except Exception as e:
            return {"error": f"Error parseando XML: {e}", "format": "xml"}

    @staticmethod
    def generate(data: dict[str, Any], root_name: str = "root") -> str:
        try:
            import xmltodict
            result = xmltodict.unparse({root_name: data}, pretty=True)
            return result
        except ImportError:
            logger.warning("xmltodict no instalado, usando generación básica")
            return XMLProcessor._basic_generate(data, root_name)
        except Exception as e:
            return f"<!-- Error generando XML: {e} -->"

    @staticmethod
    def _basic_parse(xml_string: str) -> dict[str, Any]:
        import re
        result = {}
        pattern = r"<(\w+)>([^<]+)</\1>"
        for match in re.finditer(pattern, xml_string):
            tag = match.group(1)
            content = match.group(2).strip()
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(content)
            else:
                result[tag] = content
        return {"parsed": result, "format": "xml", "parser": "basic"}

    @staticmethod
    def _basic_generate(data: dict[str, Any], root_name: str = "root", indent: int = 0) -> str:
        indent_str = "  " * indent
        lines = [f"{indent_str}<{root_name}>"]
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(XMLProcessor._basic_generate(value, key, indent + 1))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        lines.append(XMLProcessor._basic_generate(item, key, indent + 1))
                    else:
                        lines.append(f"{indent_str}  <{key}>{item}</{key}>")
            else:
                lines.append(f"{indent_str}  <{key}>{value}</{key}>")
        lines.append(f"{indent_str}</{root_name}>")
        return "\n".join(lines)
