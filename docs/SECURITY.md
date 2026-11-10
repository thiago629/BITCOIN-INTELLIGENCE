# Seguridad

## Principios

- Solo datos **públicos** de la blockchain y fuentes autorizadas (APIs públicas de mempool.space y blockstream.info).
- Sin custodia de fondos, sin claves privadas, sin firma ni envío de transacciones.
- Ningún secreto en el repositorio: la configuración se lee de variables de entorno (`BI_*`); `.env` está en `.gitignore`. `docker-compose.yml` exige `POSTGRES_PASSWORD` y no trae contraseña por defecto.

## Medidas implementadas (Fase 1)

| Medida | Dónde |
|---|---|
| Validación estricta de entradas (txid/hash hex de 64, direcciones mainnet base58/bech32, rangos numéricos) | `app/api/schemas.py`, rutas |
| CORS restringido: orígenes configurables, métodos `GET/POST/PATCH/DELETE` y cabeceras `Content-Type`, `X-API-Key`, `X-Request-ID` | `app/main.py` |
| Límite de peticiones por IP (ventana deslizante, 240/min por defecto) | `app/core/middleware.py` |
| Cabeceras de seguridad (`nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store`) y CSP en nginx | middleware, `frontend/nginx.conf` |
| Logs estructurados con request id; se registra la **plantilla** de la ruta, no la ruta real, para no guardar direcciones/txid consultados | `app/core/middleware.py`, `app/core/logging.py` |
| Errores sin trazas internas hacia el cliente | `app/main.py` |
| Respeto de límites de los proveedores (pausa tras 429 con `Retry-After`, *cooldown* tras fallos) | `app/services/blockchain.py` |
| Escritura (reglas de alerta) protegida con `BI_ADMIN_API_KEY` vía `X-API-Key` (comparación en tiempo constante); sin clave solo se permite en `development`. Los cambios de reglas se registran en el log de auditoría (`app.audit`) | `app/api/routes/alerts.py` |
| Límite de 100 reglas y validación de umbrales | `app/api/routes/alerts.py` |
| Contenedor del backend sin root; frontend publicado solo en `127.0.0.1` | Dockerfiles, compose |

## Riesgos conocidos / pendientes

- **Sin autenticación de usuarios** (planificada en Fase 5). La escritura usa una única clave de administración; en `development` sin clave, cualquiera con acceso a la API puede crear reglas. No exponer el backend a Internet sin un proxy con control de acceso.
- **Rate limit en memoria**: no se comparte entre réplicas; detrás de un proxy hay que configurar `--forwarded-allow-ips` para obtener la IP real del cliente.
- **Privacidad de consultas**: las direcciones buscadas se envían a los proveedores públicos. Un nodo propio (Bitcoin Core RPC / Esplora propio) lo evitaría.
- **Dependencia de terceros**: si ambos proveedores fallan no hay datos en vivo (se informa claramente; el historial sigue disponible).
- Esquema de BD sin migraciones versionadas todavía (Alembic pendiente).
