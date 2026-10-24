export interface SupabaseServerConfig {
  url: string;
  publishableKey: string;
  secretKey: string;
  rateLimitPepper: string;
}

export interface SupabasePublicConfig {
  url: string;
  publishableKey: string;
}

let cachedConfig: SupabaseServerConfig | undefined;

export class SupabaseConfigurationError extends Error {}

export function supabaseServerConfig(): SupabaseServerConfig {
  if (cachedConfig) return cachedConfig;

  const url = normalizeHttpsOrigin(requiredEnvironment("SUPABASE_URL"));
  const publishableKey = validateKey(
    requiredEnvironment("SUPABASE_PUBLISHABLE_KEY"),
    "SUPABASE_PUBLISHABLE_KEY",
  );
  const secretKey = validateKey(
    requiredEnvironment("SUPABASE_SECRET_KEY"),
    "SUPABASE_SECRET_KEY",
  );
  const rateLimitPepper = requiredEnvironment("RELAY_RATE_LIMIT_PEPPER");
  if (rateLimitPepper.length < 32) {
    throw new SupabaseConfigurationError(
      "RELAY_RATE_LIMIT_PEPPER must contain at least 32 characters",
    );
  }

  cachedConfig = { url, publishableKey, secretKey, rateLimitPepper };
  return cachedConfig;
}

export function supabasePublicConfig(): SupabasePublicConfig {
  const { url, publishableKey } = supabaseServerConfig();
  return { url, publishableKey };
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new SupabaseConfigurationError(`${name} is not configured`);
  return value;
}

function normalizeHttpsOrigin(value: string): string {
  const parsed = new URL(value);
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  ) {
    throw new SupabaseConfigurationError(
      "SUPABASE_URL must be an HTTPS origin without a path",
    );
  }
  return parsed.origin;
}

function validateKey(value: string, name: string): string {
  if (value.length < 20 || /\s/.test(value)) {
    throw new SupabaseConfigurationError(`${name} is invalid`);
  }
  return value;
}
