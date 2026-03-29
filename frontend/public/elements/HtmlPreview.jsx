import React from "react";

/**
 * Ensure the provided HTML is a full document.
 * If the server sends only a fragment, wrap it into a minimal HTML document.
 */
function ensureFullHtml(raw) {
  const hasHtmlTag = /<\s*html[\s>]/i.test(raw);
  if (hasHtmlTag) return raw;

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
  </head>
  <body>${raw}</body>
</html>`;
}

export default function HtmlIframe() {
  const raw = props?.html ?? "";
  const title = props?.title ?? "HTML Preview";

  const srcDoc = React.useMemo(() => ensureFullHtml(raw), [raw]);

  const reloadKey = React.useMemo(() => {
    return `${srcDoc.length}-${srcDoc.slice(0, 32)}`;
  }, [srcDoc]);

  return (
    <div className="w-full" style={{ height: "calc(100vh - 120px)", minHeight: "500px" }}>
      <iframe
        key={reloadKey}
        title={title}
        srcDoc={srcDoc}
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        style={{
          width: "100%",
          height: "100%",
          border: "none",
          background: "transparent"
        }}
      />
    </div>
  );
}
