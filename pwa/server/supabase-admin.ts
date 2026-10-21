import { supabaseServerConfig } from "./supabase-config.ts";

interface PostgrestErrorBody {
  code?: string;
  message?: string;
  details?: string;
  hint?: string;
}

export class SupabaseAdminError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export class SupabaseAdmin {
  private readonly config = supabaseServerConfig();
  private readonly timeoutMs: number;

  constructor(timeoutMs = 5_000) {
    this.timeoutMs = timeoutMs;
  }

  async select<T>(table: string, query: URLSearchParams): Promise<T[]> {
    return this.rest<T[]>(table, { method: "GET" }, query);
  }

  async insert<T>(table: string, value: unknown): Promise<T[]> {
    return this.rest<T[]>(table, {
      method: "POST",
      headers: { Prefer: "return=representation" },
      body: JSON.stringify(value),
    });
  }

  async update<T>(
    table: string,
    query: URLSearchParams,
    value: unknown,
  ): Promise<T[]> {
    return this.rest<T[]>(
      table,
      {
        method: "PATCH",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify(value),
      },
      query,
    );
  }

  async delete(table: string, query: URLSearchParams): Promise<void> {
    await this.rest<unknown>(table, { method: "DELETE" }, query);
  }

  async rpc<T>(name: string, argumentsValue: Record<string, unknown>): Promise<T> {
    return this.request<T>(`/rest/v1/rpc/${encodeURIComponent(name)}`, {
      method: "POST",
      body: JSON.stringify(argumentsValue),
    });
  }

  async authenticatedUserId(accessToken: string): Promise<string> {
    return this.withTimeout(async signal => {
      const response = await fetch(`${this.config.url}/auth/v1/user`, {
        method: "GET",
        headers: {
          apikey: this.config.publishableKey,
          Authorization: `Bearer ${accessToken}`,
        },
        cache: "no-store",
        signal,
      });
      if (!response.ok) {
        await response.body?.cancel();
        if (response.status !== 401 && response.status !== 403) {
          throw new SupabaseAdminError(503, "supabase_unavailable", "The authentication service is temporarily unavailable.");
        }
        throw new SupabaseAdminError(
          401,
          "realtime_auth_required",
          "A valid Realtime session is required.",
        );
      }
      const value: unknown = await response.json();
      const id = isObject(value) ? value.id : undefined;
      if (typeof id !== "string" || !UUID_PATTERN.test(id)) {
        throw new SupabaseAdminError(
          401,
          "realtime_auth_required",
          "The Realtime session is invalid.",
        );
      }
      return id;
    });
  }

  private async rest<T>(
    table: string,
    init: RequestInit,
    query?: URLSearchParams,
  ): Promise<T> {
    const suffix = query && query.size > 0 ? `?${query.toString()}` : "";
    return this.request<T>(`/rest/v1/${encodeURIComponent(table)}${suffix}`, init);
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("apikey", this.config.secretKey);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");

    return this.withTimeout(async signal => {
      const response = await fetch(`${this.config.url}${path}`, {
        ...init,
        headers,
        cache: "no-store",
        signal,
      });
      if (!response.ok) {
        let body: PostgrestErrorBody = {};
        try {
          body = (await response.json()) as PostgrestErrorBody;
        } catch {
          // Do not expose an upstream HTML response.
        }
        throw new SupabaseAdminError(
          response.status,
          body.code ?? "supabase_request_failed",
          body.message ?? "Supabase rejected the relay request.",
        );
      }
      if (response.status === 204) return undefined as T;
      return (await response.json()) as T;
    });
  }

  private async withTimeout<T>(operation: (signal: AbortSignal) => Promise<T>): Promise<T> {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeoutError = () => new SupabaseAdminError(
      503, "supabase_timeout", "The relay dependency did not respond in time.",
    );
    const deadline = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(timeoutError());
      }, this.timeoutMs);
    });
    try {
      // Keep the deadline active through response.json(), not just headers.
      // Never retry here: a timed-out write may already have been committed.
      return await Promise.race([operation(controller.signal), deadline]);
    } catch (error) {
      if (controller.signal.aborted) throw timeoutError();
      if (error instanceof SupabaseAdminError) throw error;
      throw new SupabaseAdminError(
        503, "supabase_unavailable", "The relay dependency is temporarily unavailable.",
      );
    } finally {
      clearTimeout(timer);
    }
  }
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
