// Build-time collection; no package code is imported or executed.
import { readdir, readFile, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
export async function browserNotices() {
  const chunks = ["QR Scanner browser software notices\nProject code: MIT; third-party code keeps its own license.\n"];
  const add = async (label, filename) => {
    chunks.push(`\n===== ${label} =====\n${await readFile(filename, "utf8")}\n`);
  };
  await add("QR Scanner project", path.resolve(root, "../LICENSE"));
  for (const name of ["next", "react", "react-dom", "qr-scanner"]) {
    const directory = path.join(root, "node_modules", name);
    const metadata = JSON.parse(await readFile(path.join(directory, "package.json"), "utf8"));
    const files = (await readdir(directory)).filter(file => /^license(?:\.|$)/i.test(file)).sort();
    if (!files.length) throw new Error(`Missing browser license: ${name}`);
    for (const file of files) await add(`${name} ${metadata.version} / ${file}`, path.join(directory, file));
  }
  // Next ships compiled subcomponents. Retain their separate notices too,
  // even when some are server-only, rather than declaring all of Next MIT.
  const compiled = path.join(root, "node_modules/next/dist/compiled");
  async function collect(directory) {
    for (const entry of (await readdir(directory, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.isDirectory()) await collect(path.join(directory, entry.name));
      else if (/^(license|copying|notice)(\.|$)/i.test(entry.name))
        await add(`Next compiled / ${path.relative(compiled, path.join(directory, entry.name)).replaceAll("\\", "/")}`, path.join(directory, entry.name));
    }
  }
  await collect(compiled);
  return chunks.join("");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await mkdir(path.join(root, "public/licenses"), { recursive: true });
  await writeFile(path.join(root, "public/licenses/THIRD_PARTY_NOTICES.txt"), await browserNotices());
  console.log("Browser license notices generated.");
}
