# BITCOIN INTELLIGENCE

Plataforma de inteligencia blockchain especializada en Bitcoin. Analiza datos **públicos** de la blockchain, guarda su propio historial y lo convierte en información comprensible, siempre indicando **de dónde viene cada dato y cuándo se actualizó**.

> No custodia Bitcoin, no gestiona claves privadas, no ejecuta transacciones y no atribuye identidades a direcciones sin pruebas verificables.

## Estado actual — Fase 1 (Fundación) ✅

| Área | Estado |
|---|---|
| Motor de datos (mempool.space + blockstream.info, con failover automático) | Funcional, datos reales |
| Caché con TTL y deduplicación de peticiones simultáneas | Funcional |
| Control de errores de API (timeouts, 5xx con reintentos, 429 con pausa, formato inesperado) | Funcional |
| Base de datos (historial de bloques, instantáneas de red, registro de ingesta) | SQLite (desarrollo) / PostgreSQL (Docker) |
| Ingesta periódica con relleno de huecos y gestión de reorganizaciones | Funcional |
| API REST `/api/v1` con validación de entradas y límite de peticiones | Funcional |
| Frontend: Dashboard, Blockchain Explorer (bloques, transacciones, direcciones, búsqueda), Estado del sistema | Funcional |
| Pruebas automatizadas | 37 backend + 11 frontend |

Los módulos de fases posteriores (Whale Tracker, Anomaly Detection, AI Reports…) aparecen en el menú **desactivados con su fase**, nunca como páginas vacías. Ver [docs/ROADMAP.md](docs/ROADMAP.md).

## Arranque rápido (desarrollo)

Requisitos: Python 3.12+ y Node 20+.

```bash
# Backend (http://localhost:8000, documentación OpenAPI en /api/docs)
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend (http://localhost:5173, redirige /api al backend)
cd frontend
npm install
npm run dev
```

Sin configurar nada usa SQLite local y las APIs públicas de mempool.space y blockstream.info. Toda la configuración está en [backend/.env.example](backend/.env.example).

## Con Docker (PostgreSQL)

```bash
cp .env.example .env            # y pon una contraseña larga en POSTGRES_PASSWORD
docker compose up --build       # http://localhost:8080
```

## Pruebas y calidad

```bash
cd backend && pytest -q && ruff check app tests && mypy app
cd frontend && npm run typecheck && npm test && npm run build
```

GitHub Actions ejecuta todo lo anterior en cada push y pull request ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Documentación

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — arquitectura, capas, decisiones y API.
- [docs/ROADMAP.md](docs/ROADMAP.md) — plan por fases y tareas pendientes.
- [docs/SECURITY.md](docs/SECURITY.md) — principios de seguridad y riesgos conocidos.
- [CHANGELOG.md](CHANGELOG.md) — cambios por versión.
