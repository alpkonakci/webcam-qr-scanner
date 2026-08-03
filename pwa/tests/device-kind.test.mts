import assert from "node:assert/strict";
import test from "node:test";

import { isLikelyMobileDevice } from "../lib/device-kind.ts";

const desktop = {
  userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
  platform: "Win32",
  maxTouchPoints: 0,
};

test("recognizes mobile browsers without treating desktop browsers as phones", () => {
  assert.equal(isLikelyMobileDevice(desktop), false);
  assert.equal(
    isLikelyMobileDevice({ ...desktop, userAgentDataMobile: true }),
    true,
  );
  assert.equal(
    isLikelyMobileDevice({
      ...desktop,
      userAgent: "Mozilla/5.0 (Linux; Android 15; Pixel 9)",
    }),
    true,
  );
});

test("recognizes iPad desktop-class user agents by touch capability", () => {
  assert.equal(
    isLikelyMobileDevice({
      userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)",
      platform: "MacIntel",
      maxTouchPoints: 5,
      userAgentDataMobile: false,
    }),
    true,
  );
});
