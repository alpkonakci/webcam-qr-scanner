"use strict";

// Only the API used by Next's root-directory resolver and Vite's dynamic-import
// plugin is supported. This is a different engine, not a renamed braces fork.
const tiny = require("tinyglobby");
const path = require("node:path");
const allowedOptions = new Set([
  "cwd", "onlyDirectories", "onlyFiles", "ignore", "dot", "absolute",
  "followSymbolicLinks", "caseSensitiveMatch", "braceExpansion", "extglob",
  "globstar", "deep",
]);

function checkedPatterns(patterns) {
  const list = typeof patterns === "string" ? [patterns] : patterns;
  if (!Array.isArray(list) || list.length > 1024) {
    throw new TypeError("Build glob expects a string or at most 1024 patterns");
  }
  let total = 0;
  for (const pattern of list) {
    if (typeof pattern !== "string") throw new TypeError("Build glob patterns must be strings");
    total += pattern.length;
    if (pattern.length > 8192 || total > 65536) throw new RangeError("Build glob pattern length exceeds limit");
    const nesting = [];
    for (let index = 0; index < pattern.length; index++) {
      const char = pattern[index];
      if (char === "\\") { index++; continue; }
      if (char === "{" || char === "(" || char === "[") {
        nesting.push(char);
        if (nesting.length > 64) throw new RangeError("Build glob nesting exceeds 64 levels");
      } else if ((char === "}" && nesting.at(-1) === "{") ||
                 (char === ")" && nesting.at(-1) === "(") ||
                 (char === "]" && nesting.at(-1) === "[")) {
        nesting.pop();
      }
    }
  }
  return patterns;
}

function checkedOptions(options = {}) {
  if (!options || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("Build glob options must be an object");
  }
  for (const key of Object.keys(options)) {
    if (!allowedOptions.has(key)) throw new TypeError(`Unsupported build glob option: ${key}`);
  }
  if (options.ignore !== undefined) checkedPatterns(options.ignore);
  // tinyglobby defaults to expanding bare directories; fast-glob does not.
  return { ...options, expandDirectories: false };
}

async function glob(patterns, options) {
  const groups = prepare(patterns, options);
  const results = [];
  for (const group of groups) results.push(...await tiny.glob(group.patterns, group.options));
  return normalizeResults(results);
}

function globSync(patterns, options) {
  return normalizeResults(prepare(patterns, options).flatMap(group =>
    tiny.globSync(group.patterns, group.options)));
}

function prepare(patterns, options) {
  const checked = checkedPatterns(patterns);
  const opts = checkedOptions(options);
  const list = typeof checked === "string" ? [checked] : checked;
  const negative = list.filter(pattern => pattern.startsWith("!"));
  const positive = list.filter(pattern => !pattern.startsWith("!"));
  const absolute = positive.filter(pattern => path.isAbsolute(pattern));
  const relative = positive.filter(pattern => !path.isAbsolute(pattern));
  // fast-glob preserves absolute input paths even when absolute is not set.
  return [
    ...(relative.length ? [{ patterns: [...relative, ...negative], options: opts }] : []),
    ...(absolute.length ? [{ patterns: [...absolute, ...negative], options: { ...opts, absolute: true } }] : []),
  ];
}

function normalizeResults(results) {
  // tinyglobby's directory-only results can have a trailing slash; fast-glob's
  // default markDirectories=false does not. Keep filesystem roots intact.
  return [...new Set(results.map(value => value.length > 3 ? value.replace(/\/$/, "") : value))];
}

module.exports = glob;
module.exports.glob = glob;
module.exports.async = glob;
module.exports.sync = globSync;
module.exports.globSync = globSync;
