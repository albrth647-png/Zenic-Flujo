"""
Connector SDK — Registro de Conectores (Singleton)
====================================================

Registro centralizado de conectores que permite:

- Registrar conectores automaticamente al importarlos
- Buscar conectores por nombre
- Listar todos los conectores disponibles con metadata
- Auto-descubrir conectores en un paquete Python

El registro sigue el patron Singleton thread-safe para asegurar
una unica instancia global en toda la aplicacion.

Uso tipico:
    from src.sdk.registry import ConnectorRegistry

    # Registrar un conector
    ConnectorRegistry.register(MyConnector)

    # Obtener un conector por nombre
    connector_cls = ConnectorRegistry.get("my_connector")

    # Listar todos los conectores disponibles
    all_connectors = ConnectorRegistry.list_all()

    # Auto-descubrir conectores en un paquete
    ConnectorRegistry.auto_discover("src.connectors")
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import threading
from typing import Any

from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class ConnectorRegistry:
    """
    Registro singleton que gestiona todos los conectores disponibles.

    Mantiene un diccionario de clases de conectores indexadas por nombre,
    con metadata adicional para cada uno. Implementa el patron Singleton
    thread-safe con doble check locking.

    Attributes:
        _instance: Unica instancia del registro (Singleton)
        _connectors: Diccionario de nombre -> clase de conector
        _metadata: Diccionario de nombre -> metadata del conector
    """

    _instance: ConnectorRegistry | None = None
    _lock = threading.RLock()

    def __new__(cls) -> ConnectorRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        with self._lock:
            if hasattr(self, "_initialized") and self._initialized:
                return
            self._initialized = True
            self._connectors: dict[str, type] = {}
            self._metadata: dict[str, dict[str, Any]] = {}

    def register(self, connector_class: type, override: bool = False) -> None:
        """
        Registra una clase de conector en el registro.

        Extrae la metadata del conector desde los atributos de clase
        (name, version, description, category, icon, author) y los
        almacena en el registro. Si ya existe un conector con el mismo
        nombre, lanza un error a menos que se especifique override=True.

        Args:
            connector_class: Clase del conector a registrar. Debe heredar
                           de BaseConnector o tener los atributos name, version, etc.
            override: Si True, permite sobreescribir un conector existente

        Raises:
            ValueError: Si el conector no tiene nombre o ya existe uno con el mismo nombre

        Ejemplo:
            ConnectorRegistry.register(SlackConnector)
            ConnectorRegistry.register(SlackConnector, override=True)
        """
        name = self._extract_name(connector_class)
        if not name:
            raise ValueError(f"La clase {connector_class.__name__} no tiene atributo 'name' o esta vacio")

        if name in self._connectors and not override:
            existing = self._connectors[name]
            if existing is connector_class:
                logger.debug(f"ConnectorRegistry: {name} ya esta registrado con la misma clase")
                return
            raise ValueError(
                f"Ya existe un conector registrado con nombre '{name}' "
                f"(clase existente: {existing.__name__}, clase nueva: {connector_class.__name__}). "
                f"Use override=True para sobreescribir."
            )

        self._connectors[name] = connector_class
        self._metadata[name] = self._extract_metadata(connector_class)

        logger.info(
            f"ConnectorRegistry: conector '{name}' registrado "
            f"(version={self._metadata[name].get('version', 'unknown')}, "
            f"category={self._metadata[name].get('category', 'general')})"
        )

    def get(self, name: str) -> type | None:
        """
        Obtiene una clase de conector por su nombre.

        Args:
            name: Nombre del conector a buscar

        Retorna:
            Clase del conector, o None si no esta registrado

        Ejemplo:
            connector_cls = ConnectorRegistry.get("slack")
            if connector_cls:
                instance = connector_cls()
        """
        return self._connectors.get(name)

    def get_metadata(self, name: str) -> dict[str, Any] | None:
        """
        Obtiene la metadata de un conector por su nombre.

        Args:
            name: Nombre del conector

        Retorna:
            Diccionario con la metadata del conector, o None si no existe
        """
        return self._metadata.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        """
        Lista todos los conectores registrados con su metadata.

        Retorna una lista de diccionarios, cada uno con la metadata
        completa de un conector, ordenados alfabeticamente por nombre.

        Retorna:
            Lista de diccionarios con metadata de cada conector

        Ejemplo:
            for info in ConnectorRegistry.list_all():
                print(f"{info['name']} v{info['version']} - {info['description']}")
        """
        result = []
        for name in sorted(self._connectors.keys()):
            meta = dict(self._metadata.get(name, {}))
            meta["name"] = name
            meta["class_name"] = self._connectors[name].__name__
            meta["module"] = self._connectors[name].__module__
            result.append(meta)
        return result

    def list_names(self) -> list[str]:
        """
        Lista los nombres de todos los conectores registrados.

        Retorna:
            Lista de nombres de conectores ordenados alfabeticamente
        """
        return sorted(self._connectors.keys())

    def list_by_category(self, category: str) -> list[dict[str, Any]]:
        """
        Lista conectores filtrados por categoria.

        Args:
            category: Categoria a filtrar (ej: 'messaging', 'crm', 'storage')

        Retorna:
            Lista de metadata de conectores que pertenecen a la categoria
        """
        return [
            {**meta, "name": name, "class_name": self._connectors[name].__name__}
            for name, meta in self._metadata.items()
            if meta.get("category", "general") == category
        ]

    def exists(self, name: str) -> bool:
        """
        Verifica si un conector esta registrado.

        Args:
            name: Nombre del conector a verificar

        Retorna:
            True si el conector esta registrado
        """
        return name in self._connectors

    def unregister(self, name: str) -> bool:
        """
        Elimina un conector del registro.

        Args:
            name: Nombre del conector a eliminar

        Retorna:
            True si el conector fue eliminado, False si no existia
        """
        if name in self._connectors:
            del self._connectors[name]
            self._metadata.pop(name, None)
            logger.info(f"ConnectorRegistry: conector '{name}' eliminado del registro")
            return True
        return False

    def count(self) -> int:
        """
        Retorna el numero de conectores registrados.

        Retorna:
            Numero de conectores en el registro
        """
        return len(self._connectors)

    def clear(self) -> None:
        """Elimina todos los conectores del registro."""
        self._connectors.clear()
        self._metadata.clear()
        logger.info("ConnectorRegistry: registro limpiado")

    def auto_discover(self, package_path: str) -> list[str]:
        """
        Auto-descubre conectores en un paquete Python.

        Escanea todos los modulos dentro del paquete especificado
        buscando clases que parezcan conectores (tienen el atributo
        'name' y heredan de BaseConnector o tienen _is_connector=True).

        Args:
            package_path: Ruta del paquete Python a escanear (ej: 'src.connectors')

        Retorna:
            Lista de nombres de conectores descubiertos y registrados

        Ejemplo:
            discovered = ConnectorRegistry.auto_discover("src.connectors")
            print(f"Descubiertos: {discovered}")
        """
        discovered: list[str] = []

        try:
            package = importlib.import_module(package_path)
        except ImportError:
            logger.error(f"ConnectorRegistry: paquete '{package_path}' no encontrado")
            return discovered

        package_dir = getattr(package, "__path__", None)
        if package_dir is None:
            logger.warning(f"ConnectorRegistry: '{package_path}' no es un paquete (no tiene __path__)")
            return discovered

        logger.info(f"ConnectorRegistry: escaneando paquete '{package_path}'...")

        for _importer_info, module_name, is_pkg in pkgutil.walk_packages(package_dir, prefix=f"{package_path}."):
            if is_pkg:
                continue

            try:
                module = importlib.import_module(module_name)
            except Exception as e:
                logger.warning(f"ConnectorRegistry: error importando {module_name}: {e}")
                continue

            for attr_name in dir(module):
                attr = getattr(module, attr_name, None)
                if attr is None or not inspect.isclass(attr):
                    continue

                # Verificar si parece un conector
                if self._is_connector_class(attr):
                    try:
                        self.register(attr)
                        discovered.append(self._extract_name(attr))
                    except ValueError as e:
                        logger.debug(f"ConnectorRegistry: no se registro {attr_name}: {e}")

        logger.info(f"ConnectorRegistry: auto-descubrimiento completo, {len(discovered)} conector(es) encontrado(s)")
        return discovered

    def _is_connector_class(self, cls: type) -> bool:
        """
        Determina si una clase es un conector valido.

        Una clase es un conector si:
        - Tiene el atributo '_is_connector' en True, o
        - Hereda de una clase con nombre 'BaseConnector', o
        - Tiene los atributos 'name' y 'version'

        Args:
            cls: Clase a verificar

        Retorna:
            True si la clase parece un conector valido
        """
        # No registrar la clase base abstracta
        if cls.__name__ == "BaseConnector":
            return False

        # Verificar marcador explicito
        if getattr(cls, "_is_connector", False):
            return True

        # Verificar herencia de BaseConnector
        for base in inspect.getmro(cls):
            if base.__name__ == "BaseConnector":
                return True

        # Verificar atributos minimos
        has_name = hasattr(cls, "name") and isinstance(getattr(cls, "name", None), str)
        has_version = hasattr(cls, "version") and isinstance(getattr(cls, "version", None), str)
        return has_name and has_version

    def _extract_name(self, connector_class: type) -> str:
        """
        Extrae el nombre de un conector desde sus atributos de clase.

        Busca el atributo 'name' en la clase. Si no existe, genera
        un nombre a partir del nombre de la clase en snake_case.

        Args:
            connector_class: Clase del conector

        Retorna:
            Nombre del conector
        """
        name = getattr(connector_class, "name", None)
        if name and isinstance(name, str):
            return name.strip()

        # Generar nombre desde el nombre de la clase
        class_name = connector_class.__name__
        # Convertir CamelCase a snake_case
        snake_name = ""
        for i, char in enumerate(class_name):
            if char.isupper() and i > 0:
                snake_name += "_"
            snake_name += char.lower()

        # Remover sufijos comunes
        for suffix in ("_connector", "_service", "_client"):
            if snake_name.endswith(suffix):
                snake_name = snake_name[: -len(suffix)]

        return snake_name

    def _extract_metadata(self, connector_class: type) -> dict[str, Any]:
        """
        Extrae metadata completa de una clase de conector.

        Recopila los atributos de clase que definen la metadata
        del conector: name, version, description, category, icon, author.

        Args:
            connector_class: Clase del conector

        Retorna:
            Diccionario con la metadata del conector
        """
        return {
            "version": getattr(connector_class, "version", "1.0.0"),
            "description": getattr(connector_class, "description", ""),
            "category": getattr(connector_class, "category", "general"),
            "icon": getattr(connector_class, "icon", "plug"),
            "author": getattr(connector_class, "author", ""),
            "registered_at": self._now_iso(),
        }

    @staticmethod
    def _now_iso() -> str:
        """Retorna la fecha/hora actual en formato ISO 8601."""
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None

    def to_dict(self) -> dict[str, Any]:
        """
        Serializa el estado del registro a diccionario.

        Retorna:
            Diccionario con todos los conectores y su metadata
        """
        return {
            "total_connectors": self.count(),
            "connectors": self.list_all(),
            "categories": sorted({m.get("category", "general") for m in self._metadata.values()}),
        }
