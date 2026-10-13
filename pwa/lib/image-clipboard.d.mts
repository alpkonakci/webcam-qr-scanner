export const NO_CLIPBOARD_IMAGE: string;
export function pastedImage(data: DataTransfer | null): File;
export function readClipboardImage(clipboard: Pick<Clipboard, "read"> | undefined, signal: AbortSignal): Promise<Blob>;
