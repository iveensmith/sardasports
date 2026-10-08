/**
 * The image shown when a link to the site is shared (social feeds, chat apps).
 *
 * Built from the brand and the one-line promise only: no statistic, so it cannot
 * go stale or claim anything the record does not back.
 */

import { readFile } from "node:fs/promises";
import path from "node:path";
import { ImageResponse } from "next/og";

export const alt =
  "SARDASPORTS: football, basketball and tennis predictions, every one graded";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OpengraphImage() {
  // The logo is the same SVG the site header uses, inlined as a data URI.
  const logo = await readFile(
    path.join(process.cwd(), "public", "sardasports-logo-horizontal.svg"),
  );
  const logoSrc = `data:image/svg+xml;base64,${logo.toString("base64")}`;

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "72px 80px",
        background:
          "radial-gradient(ellipse 70% 90% at 78% 0%, rgba(227,188,69,0.28), rgba(9,13,18,0) 60%), #090d12",
        color: "#f4f7fa",
        fontFamily: "sans-serif",
      }}
    >
      <div style={{ display: "flex" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logoSrc} width={522} height={72} alt="SARDASPORTS" />
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        <div
          style={{
            display: "flex",
            fontSize: 84,
            fontWeight: 800,
            lineHeight: 1.04,
            letterSpacing: -2,
          }}
        >
          Football predictions,
        </div>
        <div
          style={{
            display: "flex",
            fontSize: 84,
            fontWeight: 800,
            lineHeight: 1.04,
            letterSpacing: -2,
            color: "#e3bc45",
          }}
        >
          every one graded.
        </div>
        <div
          style={{
            display: "flex",
            marginTop: 28,
            fontSize: 30,
            color: "#a3b0c0",
          }}
        >
          Free AI picks for football, basketball and tennis, on a public record.
        </div>
      </div>
    </div>,
    size,
  );
}
