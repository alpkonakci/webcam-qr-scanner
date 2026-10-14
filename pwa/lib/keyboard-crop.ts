import type { ImageCrop } from "./image-policy.mjs";

export function adjustSelection(crop: ImageCrop | null, field: keyof ImageCrop, percent: number): ImageCrop {
  const current = crop ?? { x: 0, y: 0, width: 1, height: 1 };
  if (!Number.isFinite(percent)) return current;
  const next = { ...current, [field]: Math.min(100, Math.max(0, percent)) / 100 };
  next.x = Math.min(.99, next.x);
  next.y = Math.min(.99, next.y);
  // Work in whole percentages so keyboard fields don't accumulate rounding.
  next.width = Math.min(Math.max(.01, next.width), Math.round((1 - next.x) * 100) / 100);
  next.height = Math.min(Math.max(.01, next.height), Math.round((1 - next.y) * 100) / 100);
  return next;
}
