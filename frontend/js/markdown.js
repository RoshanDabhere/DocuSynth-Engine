// Small, dependency-free Markdown parser and safe DOM renderer.

function tokenizeInlineMarkdown(text) {
  const tokens = [];
  // Match **bold**, `code`, and [Source N] citation labels produced by the LLM.
  const pattern = /(\*\*([^*]+)\*\*|`([^`]+)`|\[Source\s+(\d+)\])/gi;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) {
      tokens.push({ type: "text", text: text.slice(cursor, match.index) });
    }
    if (match[2] !== undefined) {
      tokens.push({ type: "strong", text: match[2] });
    } else if (match[3] !== undefined) {
      tokens.push({ type: "code", text: match[3] });
    } else if (match[4] !== undefined) {
      // [Source N] — carries 1-based source number so UI can link to source card
      tokens.push({ type: "citation", sourceNumber: parseInt(match[4], 10) });
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    tokens.push({ type: "text", text: text.slice(cursor) });
  }
  return tokens;
}

export function parseMarkdownBlocks(markdown) {
  const lines = String(markdown || "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^```\s*([\w+-]*)\s*$/);
    if (fence) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: "code", language: fence[1], text: codeLines.join("\n") });
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    if (unordered) {
      const items = [];
      while (index < lines.length) {
        const item = lines[index].match(/^\s*[-*]\s+(.+)$/);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      blocks.push({ type: "unordered-list", items });
      continue;
    }

    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      const items = [];
      while (index < lines.length) {
        const item = lines[index].match(/^\s*\d+[.)]\s+(.+)$/);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      blocks.push({ type: "ordered-list", items });
      continue;
    }

    const paragraphLines = [line.trim()];
    index += 1;
    while (
      index < lines.length
      && lines[index].trim()
      && !/^```/.test(lines[index])
      && !/^(#{1,3})\s+/.test(lines[index])
      && !/^\s*[-*]\s+/.test(lines[index])
      && !/^\s*\d+[.)]\s+/.test(lines[index])
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

function appendInlineMarkdown(container, text) {
  const document = container.ownerDocument;
  for (const token of tokenizeInlineMarkdown(text)) {
    if (token.type === "text") {
      container.append(document.createTextNode(token.text));
    } else if (token.type === "citation") {
      // Render [Source N] as a styled interactive badge.
      // The data-source-ref attribute is picked up by chat.js to wire click events.
      const badge = document.createElement("button");
      badge.type = "button";
      badge.className = "citation-badge";
      badge.dataset.sourceRef = String(token.sourceNumber);
      badge.textContent = `[Source\u00a0${token.sourceNumber}]`;
      badge.setAttribute("aria-label", `View source ${token.sourceNumber}`);
      container.append(badge);
    } else {
      const element = document.createElement(token.type === "strong" ? "strong" : "code");
      element.textContent = token.text;
      container.append(element);
    }
  }
}

export function renderMarkdown(container, markdown) {
  const document = container.ownerDocument;
  container.replaceChildren();
  for (const block of parseMarkdownBlocks(markdown)) {
    let element;
    if (block.type === "code") {
      element = document.createElement("pre");
      const code = document.createElement("code");
      if (block.language) code.dataset.language = block.language;
      code.textContent = block.text;
      element.append(code);
    } else if (block.type === "heading") {
      element = document.createElement(`h${block.level + 2}`);
      appendInlineMarkdown(element, block.text);
    } else if (block.type.endsWith("list")) {
      element = document.createElement(block.type === "ordered-list" ? "ol" : "ul");
      for (const item of block.items) {
        const listItem = document.createElement("li");
        appendInlineMarkdown(listItem, item);
        element.append(listItem);
      }
    } else {
      element = document.createElement("p");
      appendInlineMarkdown(element, block.text);
    }
    container.append(element);
  }
}

export { tokenizeInlineMarkdown };
