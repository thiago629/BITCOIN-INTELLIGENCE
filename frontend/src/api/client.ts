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
  return request<T>("GET", path, undefined, signal);
}

/** POST/PATCH/DELETE with a JSON body. */
export async function apiSend<T>(method: "POST" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  return request<T>(method, path, body);
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      signal,
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "No se pudo conectar con el backend de Bitcoin Intelligence.");
  }
  if (res.status === 204) return undefined as T;
  if (res.ok) return (await res.json()) as T;

  let errBody: unknown = null;
  try {
    errBody = await res.json();
  } catch {
    /* non-JSON error body */
  }
  const err = (errBody as { error?: { code?: string; message?: string; details?: string[] } } | null)?.error;
  if (err) throw new ApiError(res.status, err.code ?? "error", err.message ?? "Error", err.details ?? []);
  const detail = (errBody as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") {
    const code = res.status === 422 ? "validation_error" : res.status === 401 || res.status === 403 ? "forbidden" : "http_error";
    throw new ApiError(res.status, code, detail);
  }
  if (res.status === 422) throw new ApiError(422, "validation_error", "Parámetros no válidos");
  throw new ApiError(res.status, "http_error", `Error HTTP ${res.status}`);
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "not_found":
        return "No se encontró en la blockchain.";
      case "upstream_unavailable":
        return "Las fuentes de datos no están disponibles ahora mismo. No se muestran datos antes que mostrar datos inventados o desactualizados.";
      case "forbidden":
        return `Sin permiso para esta operación: ${error.message}`;
      case "rate_limited":
        return "Demasiadas solicitudes. Espera unos segundos.";
      default:
        return error.message;
    }
  }
  return "Error inesperado.";
}
