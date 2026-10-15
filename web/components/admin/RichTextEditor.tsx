"use client";

/**
 * The article body editor: CKEditor 4 with its full toolbar, served from this site.
 *
 * It is loaded on demand from `/ckeditor/ckeditor.js` (copied out of node_modules by
 * scripts/copy-ckeditor.mjs), so the admin page does not call a third party. What it produces is
 * HTML, which the engine rebuilds from an allow-list before storing (app/services/html_sanitize),
 * so nothing the editor, a pasted document or a hand-edited "Source" view contains is trusted.
 *
 * Buttons that cannot work or that would put unsafe or external things in a post are left off:
 * Save and Export to PDF (cloud services / a form submit), the form-field buttons, Flash and
 * Iframe (stripped on save), and spell-check as you type (sends your text to a third party).
 */

import { useEffect, useRef, useState } from "react";

interface CkEditorInstance {
  getData(): string;
  setData(html: string, options?: { callback?: () => void }): void;
  on(event: string, handler: () => void): void;
  destroy(noUpdate?: boolean): void;
}

interface CkEditorGlobal {
  replace(element: HTMLElement, config: Record<string, unknown>): CkEditorInstance;
}

declare global {
  interface Window {
    CKEDITOR?: CkEditorGlobal;
    CKEDITOR_BASEPATH?: string;
  }
}

const SCRIPT = "/ckeditor/ckeditor.js";
let loading: Promise<CkEditorGlobal> | null = null;

function loadEditor(): Promise<CkEditorGlobal> {
  if (window.CKEDITOR) return Promise.resolve(window.CKEDITOR);
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    window.CKEDITOR_BASEPATH = "/ckeditor/";
    const tag = document.createElement("script");
    tag.src = SCRIPT;
    tag.async = true;
    tag.onload = () =>
      window.CKEDITOR ? resolve(window.CKEDITOR) : reject(new Error("missing"));
    tag.onerror = () => {
      loading = null;
      reject(new Error("load failed"));
    };
    document.head.appendChild(tag);
  });
  return loading;
}

// The same arrangement as the editor the owner asked for: four rows, in this order.
const TOOLBAR = [
  [
    "Source",
    "-",
    "NewPage",
    "Preview",
    "Print",
    "-",
    "Templates",
    "-",
    "Cut",
    "Copy",
    "Paste",
    "PasteText",
    "PasteFromWord",
    "-",
    "Undo",
    "Redo",
    "-",
    "Find",
    "Replace",
    "-",
    "SelectAll",
  ],
  "/",
  [
    "Bold",
    "Italic",
    "Underline",
    "Strike",
    "Subscript",
    "Superscript",
    "-",
    "CopyFormatting",
    "RemoveFormat",
    "-",
    "NumberedList",
    "BulletedList",
    "-",
    "Outdent",
    "Indent",
    "-",
    "Blockquote",
    "CreateDiv",
    "-",
    "JustifyLeft",
    "JustifyCenter",
    "JustifyRight",
    "JustifyBlock",
    "-",
    "BidiLtr",
    "BidiRtl",
    "Language",
    "-",
    "Link",
    "Unlink",
    "Anchor",
  ],
  "/",
  ["Image", "Table", "HorizontalRule", "Smiley", "SpecialChar", "PageBreak"],
  "/",
  [
    "Styles",
    "Format",
    "Font",
    "FontSize",
    "-",
    "TextColor",
    "BGColor",
    "-",
    "Maximize",
    "ShowBlocks",
    "-",
    "About",
  ],
];

export function RichTextEditor({
  initialHtml,
  height = 300,
  register,
}: {
  initialHtml: string;
  height?: number;
  /** Called once the editor is ready, with a function that returns the current HTML. */
  register: (getHtml: () => string) => void;
}) {
  const host = useRef<HTMLTextAreaElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const registerRef = useRef(register);

  useEffect(() => {
    let cancelled = false;
    let instance: CkEditorInstance | null = null;
    loadEditor()
      .then((ckeditor) => {
        if (cancelled || !host.current) return;
        instance = ckeditor.replace(host.current, {
          toolbar: TOOLBAR,
          height,
          language: "en",
          // The package's own config.js trims the toolbar to the "standard" preset, so it is
          // skipped, and the plugins the full toolbar needs are named here (they are
          // loaded from /ckeditor/plugins on demand).
          customConfig: "",
          extraPlugins:
            "newpage,preview,print,templates,find,selectall,copyformatting,justify,bidi,language,div,smiley,pagebreak,font,colorbutton,colordialog,showblocks,indentblock",
          // The owner's toolbar minus the buttons described at the top of this file.
          removePlugins:
            "save,exportpdf,scayt,wsc,forms,flash,iframe,iframedialog",
          resize_enabled: true,
          // The browser's own spell-check underlines stay; the cloud one is off.
          disableNativeSpellChecker: false,
          // Only uploaded images can be added by upload; no server browser.
          filebrowserImageUploadUrl: "/api/engine/admin/media",
          // 4.22.1 is the last open-source release; its "not the latest" notice is not useful in
          // an admin screen and is explained in docs/deployment.md.
          versionCheck: false,
        });
        instance.on("instanceReady", () => {
          if (cancelled) return;
          registerRef.current(() => instance?.getData() ?? "");
          setState("ready");
        });
      })
      .catch(() => {
        if (!cancelled) setState("failed");
      });
    return () => {
      cancelled = true;
      try {
        instance?.destroy();
      } catch {
        /* already gone */
      }
    };
  }, [height]);

  return (
    <div>
      {state === "loading" && (
        <p className="ae-editor-note">Loading the editor…</p>
      )}
      {state === "failed" && (
        <p className="ae-editor-note ae-editor-note--error">
          The editor could not be loaded. Reload the page; if it keeps failing, the
          editor files are missing from the site build.
        </p>
      )}
      <textarea
        ref={host}
        defaultValue={initialHtml}
        aria-label="Article content"
        style={{ width: "100%", height, visibility: state === "ready" ? "visible" : "hidden" }}
      />
    </div>
  );
}
