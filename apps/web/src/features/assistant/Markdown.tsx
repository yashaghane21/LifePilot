import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Model output is untrusted input. react-markdown never renders raw HTML (a reply containing
// <script> or <img onerror=...> shows as text), and it drops javascript: links by default.
const components: Components = {
  a: ({ href, children }) => (
    // External links open in a new tab without giving that page access to this one.
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline hover:text-accent-hover">
      {children}
    </a>
  ),
  p: ({ children }) => <p className="m-0">{children}</p>,
  ul: ({ children }) => <ul className="m-0 flex list-disc flex-col gap-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="m-0 flex list-decimal flex-col gap-1 pl-6">{children}</ol>,
  h1: ({ children }) => <h3 className="m-0 text-lg font-semibold">{children}</h3>,
  h2: ({ children }) => <h3 className="m-0 text-base font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="m-0 text-[15px] font-semibold">{children}</h4>,
  code: ({ className, children }) =>
    className ? (
      <code className={`${className} font-mono text-[13px]`}>{children}</code>
    ) : (
      <code className="rounded bg-bubble px-1.5 py-0.5 font-mono text-[13px]">{children}</code>
    ),
  pre: ({ children }) => <pre className="m-0 overflow-x-auto rounded-xl bg-bubble p-4">{children}</pre>,
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table className="border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-line px-3 py-1.5 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-line px-3 py-1.5">{children}</td>,
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-3 text-[15px] leading-7">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  )
}
