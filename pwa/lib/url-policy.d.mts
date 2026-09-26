export const MAX_QR_TEXT_LENGTH: number;

export type WebUrlResult =
  | { ok: true; href: string; hostname: string; insecure: boolean }
  | { ok: false; reason: string };

export function parseWebUrl(value: unknown): WebUrlResult;
