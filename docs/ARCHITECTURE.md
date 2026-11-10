# Arquitectura

## Visión general

```
                ┌──────────────────────────── Frontend (React + TypeScript) ───────────────────────────┐
                │ Dashboard · Explorer · Estado del sistema   (TanStack Query: refresco periódico)     │
                └───────────────────────────────────────┬──────────────────────────────────────────────┘
                                                        │  /api/v1 (JSON, solo GET)
┌───────────────────────────────────────── Backend (FastAPI) ──────────────────────────────────────────┐
│ api/routes      validación de entradas · sobres {data, meta} · errores tipados · rate limit · logs   │
│      │                                                                                                │
│ services/       BlockchainService: caché TTL + single-flight · failover · salud de proveedores        │
│      │                                     ▲                                                          │
│ providers/      BlockchainProvider (contrato) ── MempoolSpaceProvider, EsploraProvider (blockstream)  │
│                                            │                                                          │
│ ingestion/      IngestionWorker (cada 60 s) ─┴──► db/ (SQLAlchemy async: SQLite | PostgreSQL)          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Capas del backend (`backend/app`)

| Capa | Responsabilidad |
|---|---|
| `domain/models.py` | Modelos independientes del proveedor. Importes **siempre en satoshis enteros**. Un dato desconocido es `None`, nunca `0`. |
| `providers/` | Un adaptador por fuente. Traduce su formato al modelo de dominio y clasifica errores (`ProviderNotFound`, `ProviderRateLimited`, `ProviderUnavailable`, `CapabilityNotSupported`). Cada proveedor declara sus **capacidades**. |
| `services/blockchain.py` | Punto único de acceso a datos. Caché por clave, deduplicación de peticiones simultáneas, orden de prioridad de proveedores, failover, pausa (*cooldown*) tras fallos repetidos o 429, y metadatos de procedencia (`DataMeta`). |
| `whales/` | Whale Tracker: `analysis.py` (niveles, enriquecimiento y capas observado / interpretación / desconocido, funciones puras), `store.py` (persistencia, consultas, evaluación de alertas), `worker.py` (ciclo cada 30 s). |
| `ingestion/worker.py` | Guarda historial que las APIs públicas no ofrecen: estadísticas por bloque y series temporales de mempool/comisiones. Cada ciclo queda registrado en `ingestion_runs`. |
| `db/` | Modelos SQLAlchemy y repositorio sin SQL específico de un motor. |
| `api/` | Rutas REST, validación, sobres de respuesta. |
| `core/` | Configuración (`BI_*`), logs JSON, middleware (request id, cabeceras de seguridad, rate limit). |

### Cómo añadir un proveedor (p. ej. Bitcoin Core RPC)

1. Crear `providers/bitcoin_core.py` implementando `BlockchainProvider` y declarando `capabilities`.
2. Registrarlo en `providers/registry.py` con una clave nueva.
3. Añadirlo a `BI_PROVIDERS` en el orden de prioridad deseado.

Nada más cambia: el servicio, la API, la ingesta y el frontend siguen funcionando igual.

## Principios de datos

- **Nunca datos inventados.** Si ninguna fuente responde, la API devuelve `503 upstream_unavailable` sin campo `data`, y la interfaz lo dice explícitamente.
- **Procedencia obligatoria.** Toda respuesta de datos en vivo incluye `meta`: `source`, `fetched_at`, `cached`, `age_seconds`, `fallback_used`. Los datos históricos indican `source: "database"`.
- **Respuestas parciales honestas.** `/network/summary` devuelve cada sección por separado con `data` o `error`.
- **Hechos vs. interpretaciones.** El Explorer muestra solo hechos observables (entradas, salidas, importes). No se atribuyen identidades.

## Whale Tracker

1. El worker de ingesta guarda los bloques; el worker de ballenas analiza los que aún no ha escaneado (6 por ciclo, más recientes primero) con **una petición por bloque** (`/v1/block/{hash}/summary`). Se omite la coinbase.
2. En cada ciclo consulta también las últimas transacciones del mempool (muestra, no cobertura total).
3. Enriquecimiento acotado (20 por ciclo, mayores primero) con el detalle completo de la transacción.
4. Las reglas de alerta se evalúan al detectar un movimiento nuevo y al confirmarse uno que estaba en el mempool. Cada regla dispara una sola vez por transacción.

El importe mostrado es la **suma de todas las salidas**: incluye el cambio que vuelve al emisor, así que es un máximo. Las interpretaciones (consolidación, pago en lote, pago con cambio…) llevan siempre método y nivel de confianza. Un error de formato en un endpoint (`ProviderBadResponse`) no pone en pausa al proveedor para el resto de operaciones.

## Política de caché (TTL)

| Dato | TTL |
|---|---|
| Altura de la cadena | 10 s |
| Bloques recientes | 20 s |
| Bloque / transacciones de un bloque | 10 min |
| Transacción confirmada / sin confirmar | 10 min / 15 s |
| Dirección | 30 s |
| Mempool / comisiones | 10 s / 15 s |
| Ajuste de dificultad | 60 s |

## API `/api/v1`

Documentación interactiva: `http://localhost:8000/api/docs`.

| Método y ruta | Descripción |
|---|---|
| `GET /health` | Estado de BD, caché, proveedores e ingesta |
| `GET /system/ingestion-runs?limit=` | Registro de ciclos de ingesta |
| `GET /network/summary` | Altura, mempool, comisiones y dificultad (secciones independientes) |
| `GET /network/tip` · `/network/mempool` · `/network/mempool/recent` · `/network/fees` · `/network/difficulty` | Estado de red |
| `GET /blocks/recent?start_height=` | Página de bloques (más recientes primero) |
| `GET /blocks/height/{height}` · `/blocks/{hash}` · `/blocks/{hash}/txs?start_index=` | Bloques |
| `GET /tx/{txid}` | Transacción con entradas, salidas, comisión y tasa |
| `GET /address/{address}` · `/address/{address}/txs?after_txid=` | Dirección: estadísticas y efecto neto por transacción |
| `GET /search?q=` | Resuelve altura, hash de bloque, txid o dirección |
| `GET /history/blocks?limit=` · `/history/network?hours=` | Historial almacenado |
| `GET /whales?min_btc=&max_btc=&since=&until=&status=&sort=&limit=&offset=` | Movimientos grandes (incluye `tracking`: umbral, niveles, cobertura y notas) |
| `GET /whales/stats?hours=` | Totales, por hora (`null` = hora no cubierta) y por nivel |
| `GET /whales/{txid}` | Detalle + análisis por capas (enriquece bajo demanda) |
| `GET/POST /alerts/rules` · `PATCH/DELETE /alerts/rules/{id}` | Reglas de alerta (escritura protegida con `X-API-Key`) |
| `GET /alerts/events?limit=&offset=` | Alertas disparadas |

Errores: `{"error": {"code", "message", "details?"}}` con `404 not_found`, `422` (validación), `429 rate_limited`, `501 not_supported`, `502 upstream_error`, `503 upstream_unavailable`.

## Base de datos

| Tabla | Contenido |
|---|---|
| `blocks` | Estadísticas por bloque (tx, tamaño, peso, comisiones, tasas). Se sustituye la fila si cambia el hash en una altura (reorganización). |
| `network_snapshots` | Instantánea por ciclo: altura, mempool, comisiones recomendadas. |
| `ingestion_runs` | Auditoría de cada ciclo: estado, bloques guardados, fuentes, error. |
| `whale_txs` | Movimientos ≥ umbral: importe, estado, bloque, origen de la detección y estadísticas de estructura. |
| `whale_scanned_blocks` | Bloques analizados por el Whale Tracker (cobertura y auditoría). |
| `alert_rules` / `alert_events` | Reglas configurables y alertas disparadas (una por regla y transacción). |

En la Fase 1 el esquema se crea al arrancar (`create_all`). Antes de producción se migrará a Alembic (ver ROADMAP).

## Frontend (`frontend/src`)

- `api/` — cliente HTTP con errores normalizados, tipos espejo del backend y hooks de TanStack Query con refresco periódico.
- `components/` — layout con navegación lateral, paneles, indicador de frescura (`Freshness`), estados de carga/error/vacío, gráficos (Recharts) con tooltip y vista en tabla accesible.
- `pages/` — Dashboard, Explorer (inicio, bloque, transacción, dirección), Estado del sistema.
- `modules.ts` — fuente única de los módulos y su fase.
