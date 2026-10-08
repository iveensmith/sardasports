/**
 * The image shown when a link to the site is shared (social feeds, chat apps).
 *
 * Built from the brand and the one-line promise only: no statistic, so it cannot
 * go stale or claim anything the record does not back.
 */

import { ImageResponse } from "next/og";

export const alt = "SARDASPORTS: football predictions, every one graded";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
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
      <div style={{ display: "flex", fontSize: 44, fontWeight: 800 }}>
        <span>SARDA</span>
        <span style={{ color: "#e3bc45" }}>SPORTS</span>
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
          Free AI picks for 1X2, over 2.5, BTTS and correct score, on a public
          record.
        </div>
      </div>
    </div>,
    size,
  );
}
