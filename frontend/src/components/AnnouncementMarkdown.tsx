import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';

interface Props {
  content: string;
  className?: string;
}

export function AnnouncementMarkdown({ content, className }: Props) {
  const classes = ['announcement-markdown', className].filter(Boolean).join(' ');

  return (
    <div className={classes}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          a: ({ children, href, ...props }) => (
            <a {...props} href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          table: ({ children, ...props }) => (
            <div className="announcement-markdown-table">
              <table {...props}>{children}</table>
            </div>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
