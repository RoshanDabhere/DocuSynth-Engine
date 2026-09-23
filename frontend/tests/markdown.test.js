import assert from "node:assert/strict";
import test from "node:test";

import { parseMarkdownBlocks, tokenizeInlineMarkdown } from "../js/markdown.js";

test("parses paragraphs, bullet lists, and fenced code blocks", () => {
  const blocks = parseMarkdownBlocks(`Summary with **evidence**.

- First point
- Second point

\`\`\`python
print("safe")
\`\`\``);

  assert.deepEqual(blocks, [
    { type: "paragraph", text: "Summary with **evidence**." },
    { type: "unordered-list", items: ["First point", "Second point"] },
    { type: "code", language: "python", text: 'print("safe")' },
  ]);
});

test("tokenizes bold and inline code without producing HTML", () => {
  assert.deepEqual(tokenizeInlineMarkdown("Use **strong** and `code`."), [
    { type: "text", text: "Use " },
    { type: "strong", text: "strong" },
    { type: "text", text: " and " },
    { type: "code", text: "code" },
    { type: "text", text: "." },
  ]);
});
