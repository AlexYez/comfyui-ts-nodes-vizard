import { useEffect, useState } from "react";

import { renderSafeMarkdown, type NativeMarkdownRenderer } from "../markdown/renderer";

export function MarkdownContent({
  markdown,
  baseUrl,
  nativeRenderer,
  onRendered
}: {
  markdown: string;
  baseUrl?: string;
  nativeRenderer?: NativeMarkdownRenderer;
  onRendered?: () => void;
}) {
  const [html, setHtml] = useState("");
  useEffect(() => { if (html) onRendered?.(); }, [html, onRendered]);

  useEffect(() => {
    let active = true;
    void renderSafeMarkdown(markdown, baseUrl, nativeRenderer).then((rendered) => {
      if (active) setHtml(rendered);
    });
    return () => {
      active = false;
    };
  }, [baseUrl, markdown, nativeRenderer]);

  return <div className="nw-markdown" dangerouslySetInnerHTML={{ __html: html }} />;
}
