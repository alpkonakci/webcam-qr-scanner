const FORMATS = ["image/png", "image/jpeg", "image/webp"];
export const NO_CLIPBOARD_IMAGE = "No image found on the clipboard. Copy the image itself (not its link), or choose an image file.";

// Only accept images from a deliberate paste. Never read text, HTML or remote URLs.
export function pastedImage(data) {
  const files = Array.from(data?.files ?? []);
  if (files.length > 1) throw new Error("Paste one image at a time.");
  if (!files.length) throw new Error(NO_CLIPBOARD_IMAGE);
  return files[0]; // The shared loader checks actual bytes, dimensions and size.
}

function cancellable(work, signal) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true; clearTimeout(timer); signal.removeEventListener("abort", abort); callback(value);
    };
    const abort = () => finish(reject, new DOMException("Cancelled", "AbortError"));
    const timer = setTimeout(() => finish(reject, new Error("Clipboard access took too long. Try Ctrl+V / ⌘V, or choose an image.")), 12000);
    work.then(value => finish(resolve, value), error => finish(reject, error));
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
  });
}

export async function readClipboardImage(clipboard, signal) {
  if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
  if (!clipboard?.read) throw new Error("Clipboard images are not supported here. Try Ctrl+V / ⌘V, or choose an image.");
  const items = await cancellable(clipboard.read(), signal);
  if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
  const images = items.filter(item => item.types.some(type => type.startsWith("image/")));
  if (images.length > 1) throw new Error("Paste one image at a time.");
  if (!images.length) throw new Error(NO_CLIPBOARD_IMAGE);
  const format = FORMATS.find(type => images[0].types.includes(type));
  if (!format) throw new Error("This clipboard image format is not supported. Choose a PNG, JPEG or WebP file.");
  return cancellable(images[0].getType(format), signal);
}
