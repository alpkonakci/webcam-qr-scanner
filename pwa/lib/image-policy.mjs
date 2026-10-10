// Inspect bytes before asking the browser to allocate a decoded image.
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const MAX_IMAGE_PIXELS = 20_000_000;
export const MAX_IMAGE_SIDE = 8192;

export function validateImageSize(width, height) {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) {
    throw new Error("This image is damaged. Choose another screenshot.");
  }
  if (width > MAX_IMAGE_SIDE || height > MAX_IMAGE_SIDE || width * height > MAX_IMAGE_PIXELS) {
    throw new Error("This image is too large. Crop it around one QR code and try again.");
  }
  return { width, height };
}

export function inspectQrImage(buffer) {
  const bytes = new Uint8Array(buffer);
  if (!bytes.length || bytes.length > MAX_IMAGE_BYTES) {
    throw new Error("Choose an image smaller than 10 MB.");
  }
  const view = new DataView(buffer);
  const tag = (offset, value) => [...value].every((c, i) => bytes[offset + i] === c.charCodeAt(0));
  const damaged = () => { throw new Error("This image is damaged. Choose another screenshot."); };
  let width, height, mime;
  if (bytes.length >= 33 && bytes.slice(0, 8).every((b, i) => b === [137, 80, 78, 71, 13, 10, 26, 10][i])) {
    if (view.getUint32(8) !== 13 || !tag(12, "IHDR")) damaged();
    width = view.getUint32(16); height = view.getUint32(20); mime = "image/png";
    let ended = false;
    for (let offset = 8; offset + 12 <= bytes.length;) {
      const length = view.getUint32(offset);
      if (length > bytes.length - offset - 12) damaged();
      if (tag(offset + 4, "acTL")) throw new Error("Choose a still screenshot, not an animated image.");
      if (tag(offset + 4, "IEND")) { ended = length === 0 && offset + 12 === bytes.length; break; }
      offset += length + 12;
    }
    if (!ended) damaged();
  } else if (bytes[0] === 255 && bytes[1] === 216) {
    mime = "image/jpeg";
    const frames = new Set([192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207]);
    for (let offset = 2; offset + 4 <= bytes.length;) {
      if (bytes[offset++] !== 255) damaged();
      while (bytes[offset] === 255) offset++;
      const marker = bytes[offset++];
      if (marker === 218 || marker === 217) break;
      if (marker === 1 || (marker >= 208 && marker <= 215)) continue;
      if (offset + 2 > bytes.length) damaged();
      const length = view.getUint16(offset);
      if (length < 2 || offset + length > bytes.length) damaged();
      if (frames.has(marker)) {
        if (length < 8) damaged();
        height = view.getUint16(offset + 3); width = view.getUint16(offset + 5); break;
      }
      offset += length;
    }
  } else if (bytes.length >= 30 && tag(0, "RIFF") && tag(8, "WEBP")) {
    mime = "image/webp";
    if (view.getUint32(4, true) + 8 !== bytes.length) damaged();
    const u24 = (o) => bytes[o] | (bytes[o + 1] << 8) | (bytes[o + 2] << 16);
    for (let offset = 12; offset + 8 <= bytes.length;) {
      const length = view.getUint32(offset + 4, true), data = offset + 8;
      if (length > bytes.length - data) damaged();
      if (tag(offset, "ANIM") || tag(offset, "ANMF")) throw new Error("Choose a still screenshot, not an animated image.");
      if (tag(offset, "VP8X")) {
        if (length !== 10) damaged();
        if (bytes[data] & 2) throw new Error("Choose a still screenshot, not an animated image.");
        width = u24(data + 4) + 1; height = u24(data + 7) + 1;
      } else if (tag(offset, "VP8 ") && width === undefined) {
        if (length < 10 || !tag(data + 3, "\x9d\x01\x2a")) damaged();
        width = view.getUint16(data + 6, true) & 16383; height = view.getUint16(data + 8, true) & 16383;
      } else if (tag(offset, "VP8L") && width === undefined) {
        if (length < 5 || bytes[data] !== 47) damaged();
        const bits = view.getUint32(data + 1, true);
        width = (bits & 16383) + 1; height = ((bits >>> 14) & 16383) + 1;
      }
      offset = data + length + (length % 2);
    }
  } else {
    throw new Error("Choose a PNG, JPEG or still WebP image. Other formats are not supported yet.");
  }
  return { ...validateImageSize(width, height), mime };
}

export function cropPixels(crop, width, height) {
  if (!crop || ![crop.x, crop.y, crop.width, crop.height].every(Number.isFinite)
      || crop.x < 0 || crop.y < 0 || crop.width <= 0 || crop.height <= 0
      || crop.x + crop.width > 1.000001 || crop.y + crop.height > 1.000001) {
    throw new Error("Select the area around one QR code first.");
  }
  const x = Math.floor(crop.x * width), y = Math.floor(crop.y * height);
  const w = Math.min(width - x, Math.ceil(crop.width * width));
  const h = Math.min(height - y, Math.ceil(crop.height * height));
  if (w < 24 || h < 24) throw new Error("Select a larger area, including the QR code's white border.");
  return { x, y, width: w, height: h };
}
