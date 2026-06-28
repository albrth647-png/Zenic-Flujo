#!/usr/bin/env python3
"""MCP Memory Server v2 - Auto-logging persistente para OpenCode.

Guarda automaticamente cada interaccion en ~/.opencode-memory/
Con session log diario para no perder nada entre sesiones.
"""
import json, sys, os, time, datetime

MEMORY_DIR = os.path.expanduser("~/.opencode-memory")
os.makedirs(MEMORY_DIR, exist_ok=True)

_LOG = open(os.path.join(MEMORY_DIR, "server.log"), "a")
SESSION_FILE = os.path.join(
    MEMORY_DIR, "session_" + datetime.datetime.now().strftime("%Y%m%d") + ".jsonl"
)


def log_error(msg: str) -> None:
    _LOG.write(f"[{datetime.datetime.now().isoformat()}] ERROR: {msg}\n")
    _LOG.flush()


def log_request(method: str, key: str, content: str = "") -> None:
    try:
        with open(SESSION_FILE, "a") as sf:
            sf.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "iso": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                        "method": method,
                        "key": key,
                        "content": content,
                    }
                )
                + "\n"
            )
    except Exception as e:
        log_error(f"session log: {e}")


def handle(req: dict):
    i = req.get("id", None)
    m = req.get("method", "")
    p = req.get("params", {})

    # Notification? No responder (MCP protocol)
    if i is None:
        return None

    if m == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": i,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
            },
        }

    if m == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": i,
            "result": {
                "tools": [
                    {
                        "name": "remember",
                        "description": "Guardar nota en memoria persistente",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["key", "content"],
                        },
                    },
                    {
                        "name": "recall",
                        "description": "Recuperar notas por prefijo",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "prefix": {"type": "string"},
                            },
                            "required": ["prefix"],
                        },
                    },
                    {
                        "name": "forget",
                        "description": "Eliminar nota",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string"},
                            },
                            "required": ["key"],
                        },
                    },
                    {
                        "name": "session_log",
                        "description": "Recuperar log del dia",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "date": {
                                    "type": "string",
                                    "description": "YYYYMMDD o vacio=hoy",
                                },
                            },
                            "required": [],
                        },
                    },
                    {
                        "name": "snapshot",
                        "description": "Guarda snapshot completo de la sesion actual (user_msg, agent_resp, contexto, archivos tocados, decision)",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "session_id": {"type": "string", "description": "ID de sesion opencode"},
                                "user_message": {"type": "string", "description": "Ultimo mensaje del usuario"},
                                "agent_response": {"type": "string", "description": "Respuesta del agente"},
                                "context": {"type": "string", "description": "Contexto relevante (archivos, decisiones, errores)"},
                                "files_touched": {"type": "array", "items": {"type": "string"}, "description": "Archivos modificados"},
                                "decision": {"type": "string", "description": "Decision tomada o pendiente"},
                                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags para busqueda (ej: bug, feature, refactor)"}
                            },
                            "required": ["user_message", "agent_response"],
                        },
                    },
                ]
            },
        }

    if m == "tools/call":
        t = p.get("name", "")
        a = p.get("arguments", {})

        if t == "remember":
            k = a.get("key", "x").replace("/", "_")
            c = a.get("content", "")
            fp = os.path.join(MEMORY_DIR, k + ".json")
            with open(fp, "w") as f:
                json.dump({"key": k, "content": c, "ts": time.time()}, f)
            log_request("remember", k, c)
            return {
                "jsonrpc": "2.0",
                "id": i,
                "result": {
                    "content": [{"type": "text", "text": "ok: " + k}]
                },
            }

        if t == "recall":
            pre = a.get("prefix", "")
            r = []
            try:
                fns = sorted(os.listdir(MEMORY_DIR))
            except Exception:
                fns = []
            for fn in fns:
                if fn.endswith(".json") and not fn.startswith("session_"):
                    try:
                        with open(os.path.join(MEMORY_DIR, fn)) as f:
                            d = json.load(f)
                        if d.get("key", "").startswith(pre):
                            r.append(d["key"] + ": " + d.get("content", ""))
                    except Exception as exc:
                        log_error(f"recall read {fn}: {exc}")
            txt = "\n".join(r) if r else "none"
            log_request("recall", pre)
            return {
                "jsonrpc": "2.0",
                "id": i,
                "result": {
                    "content": [{"type": "text", "text": txt}]
                },
            }

        if t == "forget":
            k = a.get("key", "").replace("/", "_")
            fp = os.path.join(MEMORY_DIR, k + ".json")
            if os.path.exists(fp):
                os.remove(fp)
                log_request("forget", k)
                return {
                    "jsonrpc": "2.0",
                    "id": i,
                    "result": {
                        "content": [{"type": "text", "text": "del: " + k}]
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": i,
                "result": {
                    "content": [{"type": "text", "text": "nf: " + k}]
                },
            }

        if t == "session_log":
            d = a.get("date", datetime.datetime.now().strftime("%Y%m%d"))
            sp = os.path.join(MEMORY_DIR, "session_" + d + ".jsonl")
            if os.path.exists(sp):
                try:
                    with open(sp) as sf:
                        lines = sf.readlines()
                    txt = "".join(lines[-50:]) if lines else "empty"
                except Exception as exc:
                    txt = f"error: {exc}"
            else:
                txt = "no log for " + d
            return {
                "jsonrpc": "2.0",
                "id": i,
                "result": {
                    "content": [{"type": "text", "text": txt}]
                },
            }

        if t == "snapshot":
            sid = a.get("session_id", "unknown")
            um = a.get("user_message", "")
            ar = a.get("agent_response", "")
            ctx = a.get("context", "")
            files = a.get("files_touched", [])
            decision = a.get("decision", "")
            tags = a.get("tags", [])
            ts = time.time()
            iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
            snap_key = f"snapshot_{sid}_{int(ts)}"
            snap_data = {
                "key": snap_key,
                "type": "snapshot",
                "session_id": sid,
                "timestamp": ts,
                "iso": iso,
                "user_message": um,
                "agent_response": ar,
                "context": ctx,
                "files_touched": files,
                "decision": decision,
                "tags": tags,
            }
            fp = os.path.join(MEMORY_DIR, snap_key + ".json")
            with open(fp, "w") as f:
                json.dump(snap_data, f, ensure_ascii=False)
            log_request("snapshot", snap_key, f"tags={tags} files={len(files)}")
            return {
                "jsonrpc": "2.0",
                "id": i,
                "result": {
                    "content": [{"type": "text", "text": f"snapshot saved: {snap_key}"}]
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": i,
            "error": {"code": -32601, "message": "tool not found: " + t},
        }

    return {"jsonrpc": "2.0", "id": i, "error": {"code": -32601, "message": "method not found"}}


def main():
    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            break
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as e:
            log_error(f"json parse: {e} | line={line[:200]}")
        except Exception as e:
            log_error(f"handler: {e} | line={line[:200]}")


if __name__ == "__main__":
    main()
