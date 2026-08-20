import { useEffect, useState } from "react";

import { renderSafeMarkdown, type NativeMarkdownRenderer } from "../markdown/renderer";

export function MarkdownContent({
  markdown,
  baseUrl,
  nativeRenderer
}: {
  markdown: string;
  baseUrl?: string;
  nativeRenderer?: NativeMarkdownRenderer;
}) {
  const [html, setHtml] = useState("");

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

