"use client";

import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

/**
 * 受控 markdown 渲染：rehype-sanitize 兜底 XSS，链接强制新标签 + noreferrer。
 * 用于 admin 编写的系统公告正文等可信但需要富文本的场景。
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="lv-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" />,
        }}
      >
        {children}
      </ReactMarkdown>
      <style jsx global>{`
        .lv-md { color: var(--lv-ink-2); font-size: 14px; line-height: 1.75; }
        .lv-md p { margin: 0 0 0.7em; }
        .lv-md p:last-child { margin-bottom: 0; }
        .lv-md a { color: var(--lv-accent); text-decoration: underline; text-underline-offset: 2px; }
        .lv-md strong { color: var(--lv-ink); font-weight: 600; }
        .lv-md ul, .lv-md ol { margin: 0 0 0.7em; padding-left: 1.3em; }
        .lv-md li { margin: 0.2em 0; }
        .lv-md h1, .lv-md h2, .lv-md h3 { color: var(--lv-ink); font-family: var(--lv-font-serif); margin: 0.8em 0 0.4em; line-height: 1.3; }
        .lv-md h1 { font-size: 20px; }
        .lv-md h2 { font-size: 17px; }
        .lv-md h3 { font-size: 15px; }
        .lv-md code { background: rgba(255,255,255,0.08); padding: 1px 5px; border-radius: 5px; font-size: 13px; font-family: var(--lv-font-mono); }
        .lv-md blockquote { margin: 0.6em 0; padding-left: 0.9em; border-left: 2px solid var(--lv-line); color: var(--lv-ink-3); }
        .lv-md img { max-width: 100%; border-radius: var(--lv-r-input); margin: 0.4em 0; }
        .lv-md hr { border: none; border-top: 1px solid var(--lv-line); margin: 1em 0; }
      `}</style>
    </div>
  );
}
