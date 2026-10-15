/**
 * Copies the rich-text editor (CKEditor 4.22.1, the last release under its open-source licence)
 * out of node_modules into public/ckeditor, so the admin page loads it from this site and not
 * from a third party's CDN.
 *
 * Only what the editor needs is copied: the English language file, the moono-lisa skin and the
 * plugins, without the demo pages, the other languages or the other skins (about 11 MB down to
 * a few). The result is not committed (see .gitignore); `predev` and `prebuild` run this, and
 * so does the Dockerfile, because it calls `next build` directly.
 *
 * Run:  node scripts/copy-ckeditor.mjs
 */

import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const from = join(root, "node_modules", "ckeditor4");
const to = join(root, "public", "ckeditor");

if (!existsSync(join(from, "ckeditor.js"))) {
  console.error("ckeditor4 is not installed. Run `npm install` first.");
  process.exit(1);
}

const version = JSON.parse(readFileSync(join(from, "package.json"), "utf8")).version;
const stamp = join(to, ".copied-version");
if (existsSync(stamp) && readFileSync(stamp, "utf8") === version) {
  process.exit(0); // already current
}

rmSync(to, { recursive: true, force: true });
mkdirSync(to, { recursive: true });

const keepTopLevel = new Set([
  "ckeditor.js",
  "config.js",
  "contents.css",
  "styles.js",
  "LICENSE.md",
  "lang",
  "plugins",
  "skins",
  "vendor",
]);

cpSync(from, to, {
  recursive: true,
  filter(source) {
    const relative = source.slice(from.length + 1);
    if (relative === "") return true;
    const parts = relative.split(sep);
    if (!keepTopLevel.has(parts[0])) return false;
    // The editor loads only the one language it is configured with.
    if (parts[0] === "lang" && parts.length > 1 && parts[1] !== "en.js") return false;
    // One skin, and no demo or development folders anywhere.
    if (parts[0] === "skins" && parts.length > 1 && parts[1] !== "moono-lisa") return false;
    if (parts.includes("samples") || parts.includes("dev") || parts.includes("_source")) {
      return false;
    }
    // Plugin translations: English only.
    if (parts[0] === "plugins" && parts.includes("lang")) {
      const at = parts.indexOf("lang");
      if (parts.length > at + 1 && parts[at + 1] !== "en.js") return false;
    }
    return true;
  },
});

writeFileSync(stamp, version);
console.log(`ckeditor ${version} copied to public/ckeditor`);
