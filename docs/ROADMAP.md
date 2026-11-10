# Plan técnico por fases

## Fase 1 — Fundación ✅ (v0.1.0)

Arquitectura modular, motor de datos con proveedores intercambiables, caché, failover, base de datos, ingesta periódica, API REST, Dashboard, Blockchain Explorer, Estado del sistema, pruebas y CI.

**Pendiente de la Fase 1 (antes de producción):**
- Migraciones con Alembic en lugar de `create_all`.
- Verificar el stack Docker completo con PostgreSQL (el `docker-compose.yml` está validado sintácticamente, pero aún no se ha construido ni ejecutado: Docker no estaba en marcha en la máquina de desarrollo).
- Rate limit y caché compartidos (Redis) si se despliegan varias réplicas del backend.
- Política de retención del historial (`network_snapshots` crece ~1.440 filas/día).

## Fase 2 — Inteligencia blockchain

- **Whale Tracker**: ingesta de transacciones de cada bloque nuevo (y de `mempool/recent`) → tabla de movimientos que superan umbrales configurables; filtros por fecha/importe; historial; distinción explícita *observado / interpretación / desconocido* (p. ej. "salida de cambio probable" es interpretación, nunca hecho).
- **Alerts**: reglas configurables (umbral BTC, tasa de comisión, tamaño de mempool) evaluadas por el worker; historial de alertas disparadas.
- **Data Intelligence**: métricas agregadas por periodo (tx/día, comisiones/día, tamaño de bloques) sobre el historial almacenado.

## Fase 3 — Análisis avanzado

- **Anomaly Detection**: métodos estadísticos explicables (z-score robusto con mediana/MAD, ventanas móviles, comparación con el mismo periodo histórico). Cada alerta incluye el dato que la provocó, la línea base, la puntuación y sus limitaciones. Interfaz `Detector` preparada para modelos de ML.
- **Network Intelligence**: grafo de flujos observables entre transacciones (salidas gastadas → entradas), visualización de N saltos, sin heurísticas de atribución presentadas como hechos.
- **Bitcoin Intelligence Engine**: correlación de eventos, línea temporal y sistema de evidencias (dato original, fuente, fecha, método, confianza).

## Fase 4 — Inteligencia artificial

- **AI Reports** diarios, semanales y personalizados. La IA recibe **solo datos estructurados** de los módulos (con su `meta`) y redacta; las cifras se verifican contra los datos de entrada antes de publicar el informe.

## Fase 5 — Negocio y seguridad

- Autenticación, usuarios y organizaciones, roles y permisos.
- Planes de suscripción configurables con límites por plan y registro de uso (sin cobros reales sin autorización expresa).
- Panel de administración.
- Auditoría de seguridad completa (ver [SECURITY.md](SECURITY.md)).

## Ventaja competitiva (líneas de investigación)

1. **Procedencia verificable en cada cifra** (fuente, hora, método) — algo que la mayoría de exploradores no ofrece y que es imprescindible para informes profesionales.
2. **Historial propio**: series temporales de mempool y comisiones que las APIs públicas no guardan, base para anomalías y comparativas.
3. **Separación estricta hecho / interpretación / desconocido**, útil para analistas y para uso legal/compliance.
4. **Independencia de proveedor**: failover automático y, más adelante, nodo propio (Bitcoin Core RPC) para no depender de terceros.
