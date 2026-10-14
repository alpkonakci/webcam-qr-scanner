export interface HomeScreenSignals {
  userAgent: string;
  platform: string;
  maxTouchPoints: number;
  standalone: boolean;
}
export interface HomeScreenContext { platform: "ios" | "android" | "other"; installed: boolean }

export function homeScreenContext(signals: HomeScreenSignals): HomeScreenContext {
  const ios = /iPhone|iPad|iPod/i.test(signals.userAgent) ||
    (signals.platform === "MacIntel" && signals.maxTouchPoints > 1);
  return { platform: ios ? "ios" : /Android/i.test(signals.userAgent) ? "android" : "other",
    installed: signals.standalone };
}
