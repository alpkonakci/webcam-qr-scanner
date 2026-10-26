export const MAX_IMAGE_BYTES: number;
export const MAX_IMAGE_PIXELS: number;
export const MAX_IMAGE_SIDE: number;
export interface ImageCrop { x: number; y: number; width: number; height: number }
export function validateImageSize(width: number, height: number): { width: number; height: number };
export function inspectQrImage(buffer: ArrayBuffer): { width: number; height: number; mime: string };
export function cropPixels(crop: ImageCrop | null, width: number, height: number): ImageCrop;
