# Build glob compatibility adapter

The npm `fast-glob` override routes the two installed build-tool call sites to
this private package. It uses **tinyglobby 0.2.17**, which depends on fdir and
picomatch, instead of fast-glob → micromatch → braces. No vulnerable braces code
is copied or renamed, and no audit advisory is suppressed.

The root development dependency uses `file:./vendor/build-glob`; the override
references that exact dependency through `$fast-glob`. A clean `npm ci` must
deduplicate both consumers to that root adapter and `npm ls --all` must pass.

Supported consumers: `@next/eslint-plugin-next`'s `globSync(rootDir,
{onlyDirectories: true})`, and `vite-plugin-dynamic-import`'s `sync(patterns,
{cwd})`. Callable asynchronous glob and the equivalent aliases are also
provided. Unsupported options fail explicitly; this is not a general-purpose
replacement for every fast-glob API (streams, task generation, object mode).
Pattern length, count and nesting are bounded before either engine entry point.

Consumer upgrades must recheck call sites and the Next/Vite builds. The adapter
stays build-only, enforced by the runtime boundary gate. Compatibility tests
exercise real consumers, extension alternatives, directory-only matching,
negative patterns, escaped characters and rejection of excessive nesting.

Upstream: https://github.com/SuperchupuDev/tinyglobby
Advisory: https://github.com/advisories/GHSA-vfj7-8cjw-p6xm
