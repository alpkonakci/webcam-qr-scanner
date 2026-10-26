"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { chooseLanguage, translate, type Language } from "./i18n-core";
export { translate, chooseLanguage } from "./i18n-core";
export type { Language } from "./i18n-core";
type Translator = (text: string, values?: Record<string, string | number>) => string;
const Locale = createContext<{ language: Language; tr: Translator; setLanguage(language: Language): void }>({
  language: "en", tr: (text, values) => translate(text, "en", values), setLanguage: () => {},
});
const STORAGE_KEY = "wqrs-ui-language";
export function LocaleProvider({ children, initialLanguage }: { children: ReactNode; initialLanguage?: Language }) {
  const [language, setValue] = useState<Language>(initialLanguage ?? "en");
  useEffect(() => {
    if (initialLanguage) return;
    let saved: string | null = null;
    try { saved = localStorage.getItem(STORAGE_KEY); } catch { /* Storage may be disabled. */ }
    const selected = chooseLanguage(saved, navigator.language);
    queueMicrotask(() => setValue(selected));
  }, [initialLanguage]);
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  const setLanguage = useCallback((value: Language) => {
    setValue(value);
    try { localStorage.setItem(STORAGE_KEY, value); } catch { /* Session language still works. */ }
  }, []);
  const tr = useCallback<Translator>((text, values) => translate(text, language, values), [language]);
  const value = useMemo(() => ({ language, tr, setLanguage }), [language, tr, setLanguage]);
  return <Locale.Provider value={value}>{children}</Locale.Provider>;
}
export function useLocale() { return useContext(Locale); }
