import "server-only";

import { KrailApiClient, KrailApiClientError } from "./client";
import type { ApiError, Resource } from "./types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

/** Server-side provider boundary; keep the API origin off the browser contract. */
export function createServerKrailApiClient() {
  const configured = process.env.KRAIL_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;
  let baseUrl: string;
  try {
    const url = new URL(configured);
    if (url.protocol !== "http:" && url.protocol !== "https:") throw new Error("unsupported protocol");
    baseUrl = url.toString().replace(/\/$/, "");
  } catch {
    // This is server configuration, never a request-controlled redirect target.
    throw new Error("KRAIL_API_BASE_URL must be an absolute http(s) URL.");
  }
  return new KrailApiClient({ baseUrl });
}

export async function asResource<T>(operation: () => Promise<T>): Promise<Resource<T>> {
  try {
    const data = await operation();
    return { state: "ready", data };
  } catch (error) {
    const apiError: ApiError = error instanceof KrailApiClientError
      ? error
      : { code: "unknown_error", message: "An unexpected error occurred." };
    return { state: "error", error: apiError };
  }
}

export function unavailable<T>(message: string): Resource<T> {
  return { state: "unavailable", message };
}
