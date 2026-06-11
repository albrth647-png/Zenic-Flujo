"""
Workflow Determinista — Redis Service (Singleton Sync)
======================================================

Servicio de Redis para caching, PubSub, sesiones, rate limiting y locking.
Sigue el patron Singleton thread-safe de DatabaseManager.
Usa el cliente sincrono redis-py.

Configuracion via variables de entorno:
- WFD_REDIS_URL: URL de conexion (default: redis://localhost:6379/0)
- WFD_REDIS_PASSWORD: Password opcional
- WFD_REDIS_SOCKET_TIMEOUT: Timeout de socket en segundos (default: 5)
- WFD_REDIS_SOCKET_CONNECT_TIMEOUT: Timeout de conexion en segundos (default: 5)

Caracteristicas:
- Singleton thread-safe con doble check locking
- Cache: get, set, delete, exists, expire, ttl
- Cache JSON: get_json, set_json con serializacion automatica
- PubSub: publish, subscribe, unsubscribe
- Sesiones: set_session, get_session, delete_session
- Rate limiting: check_rate_limit, increment_counter
- Locking distribuido: acquire_lock, release_lock
- Health check: ping
- Pipeline para operaciones batch
- Cierre elegante de conexion
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

from src.config import PRODUCTION
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# Prefijo para claves de sesion
_SESSION_PREFIX = "session:"
# Prefijo para rate limiting
_RATE_LIMIT_PREFIX = "ratelimit:"
# Prefijo para contadores
_COUNTER_PREFIX = "counter:"
# Prefijo para locks
_LOCK_PREFIX = "lock:"


class RedisService:
    """Singleton sincrono que gestiona la conexion a Redis."""

    _instance: RedisService | None = None
    _lock = threading.RLock()

    def __new__(cls) -> RedisService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            self._url: str = os.environ.get("WFD_REDIS_URL", "redis://localhost:6379/0")
            self._password: str | None = os.environ.get("WFD_REDIS_PASSWORD", None)
            self._socket_timeout: int = int(os.environ.get("WFD_REDIS_SOCKET_TIMEOUT", "5"))
            self._socket_connect_timeout: int = int(os.environ.get("WFD_REDIS_SOCKET_CONNECT_TIMEOUT", "5"))
            self._client: Any = None  # redis.Redis
            self._pubsub: Any = None  # redis.client.PubSub
            self._subscriptions: dict[str, Any] = {}  # channel -> callback

    # ── Conexion ─────────────────────────────────────────────

    def _get_client(self) -> Any:
        """Obtiene el cliente Redis, creandolo si es necesario."""
        if self._client is not None:
            return self._client

        try:
            import redis

            self._client = redis.Redis.from_url(
                self._url,
                password=self._password,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_connect_timeout,
                decode_responses=True,
            )
            # Verificar conexion
            self._client.ping()
            logger.info(f"Redis conectado: {self._url}")

        except ImportError:
            raise ImportError("redis no esta instalado. Instalalo con: pip install redis>=5.0.0") from None
        except Exception as e:
            logger.error(f"Error conectando a Redis: {e}")
            if PRODUCTION:
                raise
            # En desarrollo, permitir que continue sin conexion
            logger.warning("Modo desarrollo: Redis no disponible, operaciones fallaran")
            # Crear cliente de todas formas para que los metodos puedan manejar el error
            try:
                import redis

                self._client = redis.Redis.from_url(
                    self._url,
                    password=self._password,
                    socket_timeout=self._socket_timeout,
                    socket_connect_timeout=self._socket_connect_timeout,
                    decode_responses=True,
                )
            except ImportError:
                raise ImportError("redis no esta instalado. Instalalo con: pip install redis>=5.0.0") from None

        return self._client

    # ── Cache — Operaciones basicas ──────────────────────────

    def get(self, key: str) -> str | None:
        """
        Obtiene un valor del cache.

        Args:
            key: Clave a buscar

        Returns:
            Valor como string o None si no existe
        """
        try:
            client = self._get_client()
            value = client.get(key)
            return value
        except Exception as e:
            logger.error(f"Redis get error para key={key}: {e}")
            return None

    def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """
        Establece un valor en el cache.

        Args:
            key: Clave
            value: Valor como string
            ttl: Tiempo de vida en segundos (opcional)

        Returns:
            True si se establecio correctamente
        """
        try:
            client = self._get_client()
            result = client.setex(key, ttl, value) if ttl is not None else client.set(key, value)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis set error para key={key}: {e}")
            return False

    def delete(self, key: str) -> int:
        """
        Elimina una clave del cache.

        Args:
            key: Clave a eliminar

        Returns:
            Numero de claves eliminadas (0 o 1)
        """
        try:
            client = self._get_client()
            return client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error para key={key}: {e}")
            return 0

    def exists(self, key: str) -> bool:
        """
        Verifica si una clave existe en el cache.

        Args:
            key: Clave a verificar

        Returns:
            True si la clave existe
        """
        try:
            client = self._get_client()
            return bool(client.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error para key={key}: {e}")
            return False

    def expire(self, key: str, ttl: int) -> bool:
        """
        Establece el TTL de una clave existente.

        Args:
            key: Clave
            ttl: Tiempo de vida en segundos

        Returns:
            True si se establecio correctamente
        """
        try:
            client = self._get_client()
            return bool(client.expire(key, ttl))
        except Exception as e:
            logger.error(f"Redis expire error para key={key}: {e}")
            return False

    def ttl(self, key: str) -> int:
        """
        Obtiene el TTL restante de una clave.

        Args:
            key: Clave

        Returns:
            TTL en segundos, -1 si no tiene expiracion, -2 si no existe
        """
        try:
            client = self._get_client()
            return client.ttl(key)
        except Exception as e:
            logger.error(f"Redis ttl error para key={key}: {e}")
            return -2

    # ── Cache — JSON ─────────────────────────────────────────

    def get_json(self, key: str) -> Any:
        """
        Obtiene un valor del cache deserializando JSON.

        Args:
            key: Clave a buscar

        Returns:
            Valor deserializado o None si no existe
        """
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Redis get_json: error deserializando key={key}: {e}")
            return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """
        Establece un valor en el cache serializando a JSON.

        Args:
            key: Clave
            value: Valor a serializar
            ttl: Tiempo de vida en segundos (opcional)

        Returns:
            True si se establecio correctamente
        """
        try:
            serialized = json.dumps(value, default=str, ensure_ascii=False)
            return self.set(key, serialized, ttl=ttl)
        except (TypeError, ValueError) as e:
            logger.error(f"Redis set_json: error serializando key={key}: {e}")
            return False

    # ── PubSub ───────────────────────────────────────────────

    def publish(self, channel: str, message: str) -> int:
        """
        Publica un mensaje en un canal.

        Args:
            channel: Nombre del canal
            message: Mensaje a publicar

        Returns:
            Numero de suscriptores que recibieron el mensaje
        """
        try:
            client = self._get_client()
            receivers = client.publish(channel, message)
            logger.debug(f"Publicado en {channel}: {receivers} receptores")
            return receivers
        except Exception as e:
            logger.error(f"Redis publish error en canal={channel}: {e}")
            return 0

    def subscribe(self, channel: str, callback: Any = None) -> bool:
        """
        Se suscribe a un canal.

        Args:
            channel: Nombre del canal
            callback: Funcion a llamar cuando se reciba un mensaje

        Returns:
            True si la suscripcion fue exitosa
        """
        try:
            client = self._get_client()
            if self._pubsub is None:
                self._pubsub = client.pubsub()

            self._pubsub.subscribe(channel)
            self._subscriptions[channel] = callback
            logger.info(f"Suscrito a canal: {channel}")
            return True
        except Exception as e:
            logger.error(f"Redis subscribe error en canal={channel}: {e}")
            return False

    def unsubscribe(self, channel: str) -> bool:
        """
        Se desuscribe de un canal.

        Args:
            channel: Nombre del canal

        Returns:
            True si la desuscripcion fue exitosa
        """
        try:
            if self._pubsub is not None:
                self._pubsub.unsubscribe(channel)
                self._subscriptions.pop(channel, None)
                logger.info(f"Desuscrito de canal: {channel}")
            return True
        except Exception as e:
            logger.error(f"Redis unsubscribe error en canal={channel}: {e}")
            return False

    def get_message(self, timeout: float = 0.1) -> dict | None:
        """
        Obtiene un mensaje del PubSub (no bloqueante por defecto).

        Args:
            timeout: Tiempo de espera en segundos

        Returns:
            Mensaje como dict o None
        """
        try:
            if self._pubsub is not None:
                message = self._pubsub.get_message(timeout=timeout)
                if message and message["type"] == "message":
                    return {
                        "channel": message["channel"],
                        "data": message["data"],
                    }
            return None
        except Exception as e:
            logger.error(f"Redis get_message error: {e}")
            return None

    # ── Sesiones ─────────────────────────────────────────────

    def set_session(self, session_id: str, data: dict, ttl: int = 86400) -> bool:
        """
        Almacena datos de sesion.

        Args:
            session_id: ID de la sesion
            data: Datos de la sesion como dict
            ttl: Tiempo de vida en segundos (default: 24h)

        Returns:
            True si se almaceno correctamente
        """
        key = f"{_SESSION_PREFIX}{session_id}"
        return self.set_json(key, data, ttl=ttl)

    def get_session(self, session_id: str) -> dict | None:
        """
        Obtiene datos de sesion.

        Args:
            session_id: ID de la sesion

        Returns:
            Datos de la sesion como dict o None
        """
        key = f"{_SESSION_PREFIX}{session_id}"
        return self.get_json(key)

    def delete_session(self, session_id: str) -> bool:
        """
        Elimina datos de sesion.

        Args:
            session_id: ID de la sesion

        Returns:
            True si se elimino correctamente
        """
        key = f"{_SESSION_PREFIX}{session_id}"
        return self.delete(key) > 0

    # ── Rate Limiting ────────────────────────────────────────

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> dict:
        """
        Verifica si una accion esta dentro del limite de frecuencia.

        Usa un sliding window con contador por ventana de tiempo.

        Args:
            key: Identificador unico de la accion (ej: "login:192.168.1.1")
            max_requests: Maximo de requests permitidas en la ventana
            window_seconds: Tamano de la ventana en segundos

        Returns:
            dict con allowed (bool), remaining (int), reset_at (int)
        """
        redis_key = f"{_RATE_LIMIT_PREFIX}{key}"
        try:
            client = self._get_client()
            pipe = client.pipeline(True)

            now = int(time.time())
            window_start = now - window_seconds

            # Usar sorted set para sliding window
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {str(now): now})
            pipe.expire(redis_key, window_seconds)

            results = pipe.execute()
            current_count = results[1]

            allowed = current_count < max_requests
            remaining = max(0, max_requests - current_count - 1)

            return {
                "allowed": allowed,
                "remaining": remaining if allowed else 0,
                "reset_at": now + window_seconds,
                "current_count": current_count + 1,
            }
        except Exception as e:
            logger.error(f"Redis check_rate_limit error para key={key}: {e}")
            # En caso de error, permitir la accion (fail open)
            return {"allowed": True, "remaining": max_requests, "reset_at": 0, "current_count": 0}

    def increment_counter(self, key: str, ttl: int | None = None) -> int:
        """
        Incrementa un contador atomicamente.

        Args:
            key: Nombre del contador
            ttl: Tiempo de vida en segundos (opcional)

        Returns:
            Nuevo valor del contador
        """
        redis_key = f"{_COUNTER_PREFIX}{key}"
        try:
            client = self._get_client()
            value = client.incr(redis_key)
            if ttl is not None and value == 1:
                client.expire(redis_key, ttl)
            return value
        except Exception as e:
            logger.error(f"Redis increment_counter error para key={key}: {e}")
            return 0

    # ── Distributed Locking ──────────────────────────────────

    def acquire_lock(self, name: str, timeout: int = 10) -> str | None:
        """
        Adquiere un lock distribuido.

        Args:
            name: Nombre del lock
            timeout: Tiempo maximo de retencion en segundos

        Returns:
            Token del lock (para liberarlo) o None si no se pudo adquirir
        """
        redis_key = f"{_LOCK_PREFIX}{name}"
        token = str(uuid.uuid4())
        try:
            client = self._get_client()
            acquired = client.set(redis_key, token, nx=True, ex=timeout)
            if acquired:
                logger.debug(f"Lock adquirido: {name} (token={token})")
                return token
            return None
        except Exception as e:
            logger.error(f"Redis acquire_lock error para name={name}: {e}")
            return None

    def release_lock(self, name: str, token: str | None = None) -> bool:
        """
        Libera un lock distribuido.

        Usa un script Lua para asegurar que solo el propietario puede liberar.
        Si no se proporciona token, se fuerza la liberacion (usar con cuidado).

        Args:
            name: Nombre del lock
            token: Token del lock obtenido al adquirirlo

        Returns:
            True si se libero correctamente
        """
        redis_key = f"{_LOCK_PREFIX}{name}"

        if token is None:
            # Forzar liberacion (peligroso en produccion)
            try:
                client = self._get_client()
                client.delete(redis_key)
                logger.warning(f"Lock forzado liberado: {name}")
                return True
            except Exception as e:
                logger.error(f"Redis release_lock (force) error para name={name}: {e}")
                return False

        # Script Lua para liberacion segura: solo si el token coincide
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            client = self._get_client()
            result = client.eval(lua_script, 1, redis_key, token)
            released = result == 1
            if released:
                logger.debug(f"Lock liberado: {name}")
            else:
                logger.warning(f"Lock no liberado (token incorrecto o expirado): {name}")
            return released
        except Exception as e:
            logger.error(f"Redis release_lock error para name={name}: {e}")
            return False

    # ── Pipeline ─────────────────────────────────────────────

    def pipeline(self) -> Any:
        """
        Crea un pipeline Redis para operaciones batch.

        Returns:
            Objeto pipeline de redis-py

        Uso:
            pipe = redis_service.pipeline()
            pipe.set("key1", "val1")
            pipe.set("key2", "val2")
            pipe.get("key1")
            results = redis_service.execute_pipeline(pipe)
        """
        client = self._get_client()
        return client.pipeline(True)

    def execute_pipeline(self, pipe: Any) -> list[Any]:
        """
        Ejecuta un pipeline y retorna los resultados.

        Args:
            pipe: Pipeline con comandos encolados

        Returns:
            Lista de resultados de cada comando
        """
        try:
            return pipe.execute()
        except Exception as e:
            logger.error(f"Redis pipeline execute error: {e}")
            return []

    # ── Health Check ─────────────────────────────────────────

    def ping(self) -> bool:
        """
        Verifica la conexion a Redis.

        Returns:
            True si la conexion esta activa
        """
        try:
            client = self._get_client()
            return client.ping()
        except Exception as e:
            logger.error(f"Redis ping fallido: {e}")
            return False

    def get_info(self) -> dict:
        """
        Retorna informacion del servidor Redis.

        Returns:
            dict con informacion del servidor
        """
        try:
            client = self._get_client()
            info = client.info()
            return {
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "db_size": client.dbsize(),
            }
        except Exception as e:
            logger.error(f"Redis get_info error: {e}")
            return {"error": str(e)}

    # ── Cierre ───────────────────────────────────────────────

    def close(self) -> None:
        """Cierra la conexion a Redis de forma elegante."""
        if self._pubsub is not None:
            try:
                self._pubsub.unsubscribe()
                self._pubsub.close()
            except Exception as e:
                logger.warning(f"Error cerrando PubSub: {e}")
            self._pubsub = None
            self._subscriptions.clear()

        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error cerrando cliente Redis: {e}")
            self._client = None
            logger.info("Redis conexion cerrada")
