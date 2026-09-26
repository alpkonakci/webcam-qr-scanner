import type { SenderCredentials } from "./wqrs";

const DATABASE_NAME = "webcam-qr-scanner";
const DATABASE_VERSION = 1;
const PAIR_STORE = "paired-pcs";

interface StoredPairRecord extends SenderCredentials {
  id: string;
}

export async function savePair(credentials: SenderCredentials): Promise<void> {
  const database = await openDatabase();
  try {
    await transactionDone(
      database,
      "readwrite",
      (store) => store.put({ ...credentials, id: credentials.pairId } satisfies StoredPairRecord),
    );
  } finally {
    database.close();
  }
}

export async function listPairs(): Promise<SenderCredentials[]> {
  const database = await openDatabase();
  try {
    const records = await transactionDone<StoredPairRecord[]>(
      database,
      "readonly",
      (store) => store.getAll(),
    );
    return records
      .filter(isValidStoredPair)
      .sort((left, right) => right.pairedAt - left.pairedAt)
      .map((record) => ({
        relayOrigin: record.relayOrigin,
        ...(record.deviceId ? { deviceId: record.deviceId } : {}),
        pairId: record.pairId,
        senderToken: record.senderToken,
        rootKey: record.rootKey,
        pcLabel: record.pcLabel,
        keyEpoch: record.keyEpoch,
        pairedAt: record.pairedAt,
      }));
  } finally {
    database.close();
  }
}

export async function getMostRecentPair(): Promise<SenderCredentials | null> {
  return (await listPairs())[0] ?? null;
}

export async function removePair(pairId: string): Promise<void> {
  const database = await openDatabase();
  try {
    await transactionDone(database, "readwrite", (store) => store.delete(pairId));
  } finally {
    database.close();
  }
}

export function defaultPhoneLabel(): string {
  if (typeof navigator === "undefined") return "My phone";
  const agent = navigator.userAgent.toLowerCase();
  if (/iphone|ipad|ipod/.test(agent)) return "My iPhone";
  if (agent.includes("android")) return "My Android phone";
  return "My phone";
}

function openDatabase(): Promise<IDBDatabase> {
  if (!("indexedDB" in globalThis)) {
    return Promise.reject(new Error("Secure browser storage is unavailable."));
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(PAIR_STORE)) {
        database.createObjectStore(PAIR_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Browser storage could not be opened."));
    request.onblocked = () => reject(new Error("Browser storage upgrade is blocked by another tab."));
  });
}

function transactionDone<T = IDBValidKey>(
  database: IDBDatabase,
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(PAIR_STORE, mode);
    const request = operation(transaction.objectStore(PAIR_STORE));
    let result: T;
    request.onsuccess = () => {
      result = request.result;
    };
    request.onerror = () => reject(request.error ?? new Error("Browser storage request failed."));
    transaction.oncomplete = () => resolve(result);
    transaction.onerror = () => reject(transaction.error ?? new Error("Browser storage transaction failed."));
    transaction.onabort = () => reject(transaction.error ?? new Error("Browser storage transaction was cancelled."));
  });
}

function isValidStoredPair(value: unknown): value is StoredPairRecord {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Partial<StoredPairRecord>;
  return (
    typeof record.id === "string" &&
    record.id === record.pairId &&
    isBase64Url(record.pairId, 22) &&
    isBase64Url(record.senderToken, 43) &&
    typeof record.relayOrigin === "string" &&
    record.relayOrigin.startsWith("https://") &&
    (record.deviceId === undefined || isBase64Url(record.deviceId, 22)) &&
    typeof record.pcLabel === "string" &&
    record.pcLabel.length > 0 &&
    record.pcLabel.length <= 80 &&
    record.keyEpoch === 1 &&
    typeof record.pairedAt === "number" &&
    record.rootKey instanceof CryptoKey &&
    record.rootKey.type === "secret" &&
    record.rootKey.extractable === false &&
    record.rootKey.algorithm.name === "HKDF" &&
    record.rootKey.usages.includes("deriveKey")
  );
}

function isBase64Url(value: unknown, characters: number): value is string {
  return typeof value === "string" && value.length === characters && /^[A-Za-z0-9_-]+$/.test(value);
}
