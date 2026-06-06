import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const DEFAULT_IMAGE_ALT = "";
const DEFAULT_IMAGE_SRC = "";
const DEFAULT_PROGRESS_TEXT = "正在检索证据";

/**
 * Markdown 回答区的 props。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
interface MarkdownAnswerProps {
  content: string;
  isStreaming: boolean;
  progressText?: string;
}

/**
 * Markdown 回答区。
 *
 * @param props - content 为回答内容，isStreaming 控制生成中提示
 * @returns 回答内容 UI；流式空内容时不渲染
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function MarkdownAnswer({ content, isStreaming, progressText }: MarkdownAnswerProps) {
  const trimmedContent = content.trim();
  return trimmedContent || !isStreaming ? (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs transition-shadow hover:shadow-sm">
      {isStreaming ? (
        <div className="mb-2 inline-flex items-center gap-1.5 text-xs text-slate-500">
          <span aria-hidden="true" className="size-1.5 animate-pulse rounded-full bg-emerald-500" />
          {progressText ?? DEFAULT_PROGRESS_TEXT}
        </div>
      ) : null}
      {trimmedContent ? (
        <div className="chat-answer text-sm leading-7 text-slate-800 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold [&_h4]:text-sm [&_h4]:font-medium [&_p]:m-0 [&_ul]:m-0 [&_ol]:m-0 [&_ul]:grid [&_ul]:gap-1 [&_ol]:grid [&_ol]:gap-1 [&_ul]:pl-5 [&_ol]:pl-5 [&_blockquote]:rounded-md [&_blockquote]:border-l-2 [&_blockquote]:border-emerald-500 [&_blockquote]:bg-slate-50 [&_blockquote]:px-3 [&_blockquote]:py-2 [&_blockquote]:text-slate-500 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[0.9em] [&_pre]:max-h-44 [&_pre]:overflow-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:border-slate-200 [&_pre]:bg-slate-50 [&_pre]:p-2.5 [&_a]:font-medium [&_a]:text-emerald-700 [&_a]:no-underline hover:[&_a]:underline [&_img]:max-h-64 [&_img]:rounded-md [&_img]:border [&_img]:border-slate-200 [&_img]:bg-slate-50 [&_img]:object-contain [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_table]:rounded-md [&_table]:border [&_table]:border-slate-200 [&_table]:text-sm [&_th]:border-b [&_th]:border-slate-200 [&_th]:bg-slate-50 [&_th]:px-2.5 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_td]:border-b [&_td]:border-slate-200 [&_td]:px-2.5 [&_td]:py-2 [&_td]:text-left [&_td]:align-top">
          <ReactMarkdown
            components={{
              a: ({ children, href }) => (
                <a href={href} rel="noreferrer" target="_blank">{children}</a>
              ),
              img: ({ alt, src }) => <img alt={alt ?? DEFAULT_IMAGE_ALT} loading="lazy" src={src ?? DEFAULT_IMAGE_SRC} />,
            }}
            remarkPlugins={[remarkGfm]}
          >
            {content}
          </ReactMarkdown>
        </div>
      ) : null}
    </div>
  ) : undefined;
}
