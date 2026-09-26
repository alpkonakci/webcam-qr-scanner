export interface DeviceSignals {
  userAgent: string;
  platform: string;
  maxTouchPoints: number;
  userAgentDataMobile?: boolean;
}

export function isLikelyMobileDevice(signals: DeviceSignals): boolean {
  if (signals.userAgentDataMobile === true) return true;

  const mobileUserAgent = /Android|iPhone|iPad|iPod|Mobile/i.test(
    signals.userAgent,
  );
  const modernIPad =
    signals.platform === "MacIntel" && signals.maxTouchPoints > 1;

  return mobileUserAgent || modernIPad;
}

export function isLikelyMobileBrowser(): boolean {
  if (typeof navigator === "undefined") return false;

  const browserNavigator = navigator as Navigator & {
    userAgentData?: { mobile?: boolean };
  };

  return isLikelyMobileDevice({
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    maxTouchPoints: navigator.maxTouchPoints,
    userAgentDataMobile: browserNavigator.userAgentData?.mobile,
  });
}
