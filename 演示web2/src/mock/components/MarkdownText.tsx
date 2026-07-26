import { Fragment, useMemo, type ReactNode } from "react";

type MarkdownTextProps = {
  content: string;
  className?: string;
};

type Block =
  | { type: "paragraph"; text: string }
  | { type: "heading"; level: 3 | 4; text: string }
  | { type: "ul" | "ol"; items: string[] }
  | { type: "code"; text: string };

export function MarkdownText({ content, className = "" }: MarkdownTextProps) {
  const classes = ["markdown-text", className].filter(Boolean).join(" ");
  // parseBlocks 会逐行扫描并让 renderInline 逐字符走一遍，重新构造全部 React 元素；
  // 内容不变时没有理由重算。
  const blocks = useMemo(() => parseBlocks(content), [content]);
  return <div className={classes}>{blocks.map(renderBlock)}</div>;
}

function parseBlocks(content: string): Block[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "code", text: codeLines.join("\n") });
      index += index < lines.length ? 1 : 0;
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length <= 2 ? 3 : 4, text: heading[2] });
      index += 1;
      continue;
    }

    const unordered = /^[-*]\s+(.+)$/.exec(trimmed);
    if (unordered) {
      const items: string[] = [];
      while (index < lines.length) {
        const item = /^[-*]\s+(.+)$/.exec(lines[index].trim());
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    const ordered = /^\d+[.)]\s+(.+)$/.exec(trimmed);
    if (ordered) {
      const items: string[] = [];
      while (index < lines.length) {
        const item = /^\d+[.)]\s+(.+)$/.exec(lines[index].trim());
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length && lines[index].trim()) {
      const current = lines[index].trim();
      if (
        current.startsWith("```")
        || /^(#{1,4})\s+/.test(current)
        || /^[-*]\s+/.test(current)
        || /^\d+[.)]\s+/.test(current)
      ) {
        break;
      }
      paragraphLines.push(current);
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join("\n") });
  }

  return blocks;
}

function renderBlock(block: Block, index: number): ReactNode {
  switch (block.type) {
    case "heading": {
      const Heading = block.level === 3 ? "h3" : "h4";
      return <Heading key={`heading-${index}`}>{renderInline(block.text, `heading-${index}`)}</Heading>;
    }
    case "ul":
    case "ol": {
      const List = block.type;
      return (
        <List key={`${block.type}-${index}`}>
          {block.items.map((item, itemIndex) => (
            <li key={`${block.type}-${index}-${itemIndex}`}>{renderInline(item, `${block.type}-${index}-${itemIndex}`)}</li>
          ))}
        </List>
      );
    }
    case "code":
      return (
        <pre key={`code-${index}`}>
          <code>{block.text}</code>
        </pre>
      );
    default:
      return <p key={`paragraph-${index}`}>{renderInlineWithBreaks(block.text, `paragraph-${index}`)}</p>;
  }
}

function renderInlineWithBreaks(text: string, keyPrefix: string): ReactNode[] {
  return text.split("\n").flatMap((line, index) => {
    const nodes = renderInline(line, `${keyPrefix}-${index}`);
    if (index === 0) return nodes;
    return [<br key={`${keyPrefix}-br-${index}`} />, ...nodes];
  });
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;

  while (cursor < text.length) {
    const codeIndex = text.indexOf("`", cursor);
    const strongIndex = text.indexOf("**", cursor);
    const nextIndex = nearestMarker(codeIndex, strongIndex);

    if (nextIndex === -1) {
      nodes.push(text.slice(cursor));
      break;
    }

    if (nextIndex > cursor) {
      nodes.push(text.slice(cursor, nextIndex));
    }

    if (nextIndex === codeIndex && (strongIndex === -1 || codeIndex < strongIndex)) {
      const end = text.indexOf("`", codeIndex + 1);
      if (end === -1) {
        nodes.push(text.slice(codeIndex));
        break;
      }
      nodes.push(<code key={`${keyPrefix}-code-${key}`}>{text.slice(codeIndex + 1, end)}</code>);
      cursor = end + 1;
      key += 1;
      continue;
    }

    const end = text.indexOf("**", strongIndex + 2);
    if (end === -1) {
      nodes.push(text.slice(strongIndex));
      break;
    }
    nodes.push(
      <strong key={`${keyPrefix}-strong-${key}`}>
        {renderInline(text.slice(strongIndex + 2, end), `${keyPrefix}-strong-${key}`)}
      </strong>
    );
    cursor = end + 2;
    key += 1;
  }

  return nodes.map((node, index) => (
    typeof node === "string" ? <Fragment key={`${keyPrefix}-text-${index}`}>{node}</Fragment> : node
  ));
}

function nearestMarker(first: number, second: number) {
  if (first === -1) return second;
  if (second === -1) return first;
  return Math.min(first, second);
}
