/**
 * Makes the raster browser icons from `app/icon.svg` (itself built by
 * `scripts/build_logo_svg.py`): `app/favicon.ico` (16, 32 and 48 px) and
 * `app/apple-icon.png` (180 px, for a phone's home screen). Next serves all three from the
 * app folder and links them in every page's <head>.
 *
 *   node scripts/build-favicons.mjs
 */

import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import sharp from "sharp";

const app = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "app");
const svg = await readFile(path.join(app, "icon.svg"));
const png = (size) =>
  sharp(svg, { density: 384 }).resize(size, size).png({ compressionLevel: 9 }).toBuffer();

// An .ico is a small directory followed by the images; modern browsers accept PNG data in it.
const sizes = [16, 32, 48];
const images = await Promise.all(sizes.map(png));
const header = Buffer.alloc(6 + 16 * sizes.length);
header.writeUInt16LE(0, 0); // reserved
header.writeUInt16LE(1, 2); // type: icon
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
sizes.forEach((size, i) => {
  const at = 6 + 16 * i;
  header.writeUInt8(size, at); // width
  header.writeUInt8(size, at + 1); // height
  header.writeUInt16LE(1, at + 4); // colour planes
  header.writeUInt16LE(32, at + 6); // bits per pixel
  header.writeUInt32LE(images[i].length, at + 8);
  header.writeUInt32LE(offset, at + 12);
  offset += images[i].length;
});
await writeFile(path.join(app, "favicon.ico"), Buffer.concat([header, ...images]));
await writeFile(path.join(app, "apple-icon.png"), await png(180));
console.log("wrote favicon.ico (16, 32, 48) and apple-icon.png (180)");
