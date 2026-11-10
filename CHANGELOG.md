# Changelog

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
