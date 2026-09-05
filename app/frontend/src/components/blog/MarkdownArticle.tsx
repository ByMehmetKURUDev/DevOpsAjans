import Markdown from 'markdown-to-jsx';

type MarkdownArticleProps = {
  markdown: string;
};

const MarkdownArticle = ({ markdown }: MarkdownArticleProps) => (
  <div className="prose prose-invert prose-lg max-w-none prose-headings:text-white prose-h1:mt-0 prose-h1:text-4xl prose-h1:leading-tight prose-h2:mt-12 prose-h2:border-t prose-h2:border-white/10 prose-h2:pt-8 prose-h2:text-3xl prose-h2:leading-snug prose-h3:mt-10 prose-h3:text-2xl prose-h3:leading-snug prose-p:text-[1.06rem] prose-p:leading-8 prose-p:text-[#c4b6de] prose-li:leading-8 prose-li:text-[#c4b6de] prose-strong:text-white prose-code:rounded prose-code:bg-purple-500/15 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[0.9em] prose-code:font-medium prose-code:text-purple-200 prose-pre:rounded-2xl prose-pre:bg-[#120727] prose-pre:p-5 prose-pre:text-[#ece6ff] prose-a:text-purple-300 prose-a:decoration-purple-500/50 prose-a:underline-offset-4 hover:prose-a:text-pink-300 prose-blockquote:border-l-purple-500 prose-blockquote:text-[#b9a9d6]">
    <Markdown
      options={{
        forceBlock: true,
        overrides: {
          a: {
            props: {
              className: 'font-medium',
            },
          },
          pre: {
            props: {
              className: 'overflow-x-auto',
            },
          },
        },
      }}
    >
      {markdown}
    </Markdown>
  </div>
);

export default MarkdownArticle;