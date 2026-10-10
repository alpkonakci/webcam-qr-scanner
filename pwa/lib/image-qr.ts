import { cropPixels, inspectQrImage, MAX_IMAGE_BYTES, validateImageSize, type ImageCrop } from "./image-policy.mjs";

const TIMEOUT = 12_000;
const NO_QR = "No QR code found";
export const NO_IMAGE_QR = "No QR code was found in this area. Include its white border, crop closer or choose a sharper screenshot. Enlarging a blurred image cannot restore missing detail.";
const cancelled = () => new DOMException("Cancelled", "AbortError");

function bounded<T>(work: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const abort = () => finish(reject, cancelled());
    const timer = setTimeout(() => finish(reject, new Error("Reading took too long. Select a smaller area and try again.")), TIMEOUT);
    const finish = (callback: (value: never) => void, value: unknown) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer); signal.removeEventListener("abort", abort); callback(value as never);
    };
    work.then((value) => finish(resolve, value), (error) => finish(reject, error));
    if (signal.aborted) { abort(); return; }
    signal.addEventListener("abort", abort, { once: true });
  });
}

export interface LocalQrImage { image: HTMLImageElement; url: string; dispose(): void }

export async function loadQrImage(file: Blob, signal: AbortSignal): Promise<LocalQrImage> {
  if (file.size > MAX_IMAGE_BYTES || file.size === 0) throw new Error("Choose an image smaller than 10 MB.");
  const bytes = await bounded(file.arrayBuffer(), signal);
  if (signal.aborted) throw cancelled();
  const info = inspectQrImage(bytes);
  // Use the inspected format, never trust a filename or a supplied MIME type.
  const url = URL.createObjectURL(new Blob([bytes], { type: info.mime }));
  const image = new Image();
  const dispose = () => { image.onload = null; image.onerror = null; image.src = ""; URL.revokeObjectURL(url); };
  try {
    await bounded(new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("This image could not be opened. Choose another screenshot."));
      image.src = url;
    }), signal);
    if (signal.aborted) throw cancelled();
    validateImageSize(image.naturalWidth, image.naturalHeight);
    return { image, url, dispose };
  } catch (error) { dispose(); throw error; }
}

export async function scanQrImage(image: HTMLImageElement, crop: ImageCrop, signal: AbortSignal): Promise<string> {
  const region = cropPixels(crop, image.naturalWidth, image.naturalHeight);
  const canvas = document.createElement("canvas");
  const scale = Math.min(1, 1600 / Math.max(region.width, region.height));
  canvas.width = Math.max(1, Math.round(region.width * scale));
  canvas.height = Math.max(1, Math.round(region.height * scale));
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("Image scanning is not available in this browser.");
  context.fillStyle = "white"; context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, region.x, region.y, region.width, region.height, 0, 0, canvas.width, canvas.height);
  let engine: Awaited<ReturnType<typeof import("qr-scanner").default.createQrEngine>> | undefined;
  let disposed = false;
  const disposeEngine = () => { disposed = true; if (engine && "terminate" in engine) engine.terminate(); };
  const scan = async () => {
    const { default: QrScanner } = await import("qr-scanner");
    if (signal.aborted || disposed) throw cancelled();
    engine = await QrScanner.createQrEngine();
    if (signal.aborted || disposed) { disposeEngine(); throw cancelled(); }
    const decode = () => QrScanner.scanImage(canvas, { qrEngine: engine, returnDetailedScanResult: true });
    let first;
    try { first = await decode(); }
    catch (error) {
      if (String(error).includes(NO_QR)) throw new Error(NO_IMAGE_QR);
      throw new Error("This area could not be read. Select it again or choose another image.");
    }
    if (signal.aborted || disposed) throw cancelled();
    // Check for another detectable code instead of silently choosing one.
    const points = first.cornerPoints;
    if (points.length !== 4 || points.some(({ x, y }) => !Number.isFinite(x) || !Number.isFinite(y))) {
      throw new Error("Select a tighter area around one QR code and try again.");
    }
    context.beginPath(); context.moveTo(points[0].x, points[0].y);
    points.slice(1).forEach(({ x, y }) => context.lineTo(x, y));
    context.closePath(); context.fill();
    try {
      await decode();
    } catch (error) {
      if (signal.aborted || disposed) throw cancelled();
      if (String(error).includes(NO_QR)) return first.data;
      throw new Error("Could not check this area. Select a tighter area around one QR code.");
    }
    throw new Error("More than one QR code was found. Select only the code you want to read.");
  };
  signal.addEventListener("abort", disposeEngine, { once: true });
  try { return await bounded(scan(), signal); }
  finally { signal.removeEventListener("abort", disposeEngine); disposeEngine(); canvas.width = canvas.height = 0; }
}
