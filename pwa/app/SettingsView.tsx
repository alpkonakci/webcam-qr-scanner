"use client";
import { useLocale } from "../lib/i18n";
import { APP_VERSION, RELEASES_URL } from "../lib/app-info";
export function SettingsView({ onBack }: { onBack(): void }) {
  const { language, setLanguage, tr } = useLocale();
  return <section className="settings-panel" aria-labelledby="settings-title">
    <h1 id="settings-title" tabIndex={-1}>{tr("Settings and about")}</h1>
    <label htmlFor="ui-language">{tr("Language")}</label>
    <select id="ui-language" value={language} onChange={(e) => setLanguage(e.target.value === "tr" ? "tr" : "en")}>
      <option value="tr">Türkçe</option><option value="en">English</option>
    </select>
    <p>{tr("Version")}: <strong>{APP_VERSION}</strong></p>
    <a className="result-secondary result-secondary-enabled" href={RELEASES_URL} target="_blank" rel="noopener noreferrer">{tr("Official downloads")}</a>
    <p>{tr("MIT license · Free to use")}</p>
    <small>{tr("Preferences are saved on this device.")}</small>
    <button type="button" className="result-primary" onClick={onBack}>{tr("Back")}</button>
  </section>;
}
