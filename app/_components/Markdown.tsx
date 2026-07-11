"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Matches bare "/outputs/<session>/<file>.png"-style paths mentioned in plain
// text (not already inside a markdown link or image) so they render as
// clickable/inline images even when the model just prints the path.
const BARE_PNG_PATH = /(?<!\]\()(\/?outputs\/[^\s)]+\.(?:png|jpe?g|gif|svg))/gi;

function linkifyArtifactPaths(text: string): string {
  return text.replace(BARE_PNG_PATH, (match) => {
    const href = match.startsWith("/") ? match : `/${match}`;
    return `![${match}](${href})`;
  });
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: ({ src, alt }) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={typeof src === "string" ? src : undefined} alt={alt ?? ""} />
          ),
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {linkifyArtifactPaths(text)}
      </ReactMarkdown>
    </div>
  );
}
