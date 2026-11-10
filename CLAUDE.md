# BITCOIN INTELLIGENCE — instrucciones permanentes de trabajo

Plataforma profesional de inteligencia blockchain sobre Bitcoin (objetivo: SaaS comercial). Prioridad: calidad, fiabilidad, seguridad y valor para el cliente — no cantidad de código ni de pantallas.

## Reglas de producto (no negociables)
- Solo datos públicos y fuentes autorizadas. Sin custodia, sin claves privadas, sin ejecutar transacciones.
- **Nunca inventar datos**. Si una fuente no responde, decirlo explícitamente (la API devuelve 503 sin `data`).
- Toda cifra muestra **fuente y hora de actualización** (`meta` en la API, `Freshness` en la UI).
- No atribuir identidades a direcciones sin pruebas verificables. Distinguir hecho observado / interpretación / desconocido.
- No llamar "fraude" o "ataque" a una anomalía. Las puntuaciones de anomalía no son probabilidades de delito.
- La IA de informes solo redacta a partir de datos estructurados de los módulos.

## Forma de trabajar
- Antes de modificar: inspeccionar la estructura y conservar lo que funciona. No eliminar, sustituir ni reconstruir funcionalidades existentes sin autorización.
- Cada funcionalidad incluye: UI terminada, lógica real, conexión al backend/datos reales, validación y errores, estados de carga/vacío/error, pruebas y documentación. Nada de botones decorativos ni páginas vacías (los módulos futuros aparecen deshabilitados con su fase en `frontend/src/modules.ts`).
- Después de cada cambio, ejecutar y dejar en verde:
  - `cd backend && pytest -q && ruff check app tests && ruff format --check app tests && mypy app`
  - `cd frontend && npm run typecheck && npm test && npm run build`
- Comprobar en el navegador las pantallas afectadas con datos reales.
- Actualizar `docs/` y `CHANGELOG.md`.
- Trabajar de forma autónoma en cambios rutinarios. **Pedir autorización** antes de: borrar datos, cambios destructivos, contratar servicios, generar gastos, modificar credenciales o publicar en producción.
- Al terminar cada bloque: informe con lo desarrollado, archivos modificados, qué funciona, pruebas superadas, errores encontrados y corregidos, pendientes y siguiente paso más importante.

## Arquitectura (ver docs/ARCHITECTURE.md)
- Backend `backend/app`: `domain` (modelos, satoshis enteros, desconocido = `None`) → `providers` (un adaptador por fuente, con capacidades) → `services/blockchain.py` (único punto de acceso: caché, failover, procedencia) → `api/routes`. Historial en `db/` vía `ingestion/worker.py`.
- Nuevas fuentes de datos: implementar `BlockchainProvider` y registrarlo en `providers/registry.py`; no llamar a APIs externas desde otros sitios.
- Frontend `frontend/src`: hooks en `api/hooks.ts`, componentes comunes en `components/ui.tsx`.
- En Windows, rutas de proyecto muy largas rompen el venv de Python (DLL de SQLAlchemy): usar una ruta corta para el venv.
