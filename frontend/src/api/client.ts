export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: string[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE = "/api/v1";

/** GET a backend endpoint and normalise every failure into ApiError. */
export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "No se pudo conectar con el backend de Bitcoin Intelligence.");
  }
  if (res.ok) return (await res.json()) as T;

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error body */
  }
  const err = (body as { error?: { code?: string; message?: string; details?: string[] } } | null)?.error;
  if (err) throw new ApiError(res.status, err.code ?? "error", err.message ?? "Error", err.details ?? []);
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (res.status === 422) {
    const msg = typeof detail === "string" ? detail : "Parámetros no válidos";
    throw new ApiError(422, "validation_error", msg);
  }
  throw new ApiError(res.status, "http_error", `Error HTTP ${res.status}`);
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "not_found":
        return "No se encontró en la blockchain.";
      case "upstream_unavailable":
        return "Las fuentes de datos no están disponibles ahora mismo. No se muestran datos antes que mostrar datos inventados o desactualizados.";
      case "rate_limited":
        return "Demasiadas solicitudes. Espera unos segundos.";
      default:
        return error.message;
    }
  }
  return "Error inesperado.";
}
