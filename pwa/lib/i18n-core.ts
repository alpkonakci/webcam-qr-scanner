import catalog from "./translations.tr.json" with { type: "json" };
import englishCatalog from "./translations.en.json" with { type: "json" };
export type Language = "en" | "tr";
const dictionary: Record<string, string> = catalog;
const english: Record<string, string> = englishCatalog;
export function chooseLanguage(saved: string | null, browserLanguage = "en"): Language {
  return saved === "tr" || saved === "en" ? saved : browserLanguage.toLowerCase().startsWith("tr") ? "tr" : "en";
}
export function translate(text: string, language: Language, values?: Record<string, string | number>): string {
  const key = text.replace(/\s+/g, " ").trim();
  let result = (language === "tr" ? dictionary : english)[key] ?? text;
  if (values) result = result.replace(/\{(\w+)\}/g, (match, name: string) => String(values[name] ?? match));
  // Only known UI message templates are translated. QR text, URLs and names
  // are never sent through this function by payload views.
  if (language === "tr" && !values) {
    const received = /^(.+) received and verified the link\.$/.exec(text);
    const sending = /^Sending securely to (.+)\.\.\.$/.exec(text);
    if (received) return translate("{pc} received and verified the link.", language, { pc: received[1] });
    if (sending) return translate("Sending securely to {pc}...", language, { pc: sending[1] });
  }
  return result;
}
