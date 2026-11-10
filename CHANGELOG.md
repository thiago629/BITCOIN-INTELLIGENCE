# Changelog

## 0.2.0 — 2026-11-10 — Fase 2: Whale Tracker y Alerts

### Añadido
- **Whale Tracker**: detección de transacciones con salidas totales ≥ umbral configurable (`BI_WHALE_MIN_BTC`, 100 BTC por defecto) con una sola petición por bloque (`/v1/block/{hash}/summary` de mempool.space) y muestreo del mempool.
- Clasificación por niveles configurables (`BI_WHALE_TIERS_BTC`): Grande ≥100, Muy grande ≥1.000, Ballena ≥10.000 BTC.
- Análisis por capas de cada movimiento: **observado** (hechos), **interpretación** (heurísticas con método y confianza) y **desconocido**. Sin atribución de identidades.
- Enriquecimiento automático (estructura de entradas/salidas, importe que vuelve a direcciones de origen) y bajo demanda en la vista de detalle.
- Historial con filtros por fecha, importe, estado y orden; estadísticas de 24 h por hora y por nivel con **ventana de cobertura** explícita (las horas aún no analizadas se muestran como desconocidas, no como cero).
- **Alerts**: reglas configurables (umbral, incluir o no sin confirmar, activar/pausar, eliminar conservando el historial), evaluadas al detectar o confirmar un movimiento; historial de alertas disparadas.
- Protección de escritura: `BI_ADMIN_API_KEY` (cabecera `X-API-Key`); sin clave, la escritura solo se permite en `development`.
- Dashboard: panel de grandes movimientos recientes.

### Corregido
- mempool.space devuelve `vsize` fraccionario en el resumen de bloque; se redondea hacia arriba.
- Un error de formato en un endpoint ya no pone en pausa al proveedor completo (`ProviderBadResponse`): se registra y se usa el respaldo solo para esa operación.
- Importes en los textos de análisis con formato español, igual que la interfaz.

## 0.1.0 — 2026-11-10 — Fase 1: Fundación

### Añadido
- Backend FastAPI con arquitectura por capas (dominio, proveedores, servicios, ingesta, BD, API).
- Proveedores mempool.space y blockstream.info (Esplora) con failover automático, reintentos, pausa ante 429 y detección de respuestas mal formadas.
- Caché TTL con deduplicación de peticiones simultáneas y metadatos de procedencia en cada respuesta.
- Persistencia con SQLAlchemy async (SQLite en desarrollo, PostgreSQL en Docker): historial de bloques, instantáneas de red y registro de ingesta.
- Worker de ingesta periódica con relleno de huecos (144 bloques) y gestión de reorganizaciones.
- API REST `/api/v1`: red, bloques, transacciones, direcciones, búsqueda, historial, salud.
- Seguridad base: validación de entradas, rate limit por IP, cabeceras de seguridad, logs JSON sin datos consultados.
- Frontend React + TypeScript: Dashboard, Blockchain Explorer (bloques, transacciones, direcciones, búsqueda), Estado del sistema; tema oscuro, responsive, gráficos con tooltip y vista en tabla.
- 37 pruebas de backend (pytest) y 11 de frontend (Vitest + Testing Library); ruff, mypy y tsc sin errores.
- Docker (backend, frontend con nginx, PostgreSQL) y CI en GitHub Actions.
