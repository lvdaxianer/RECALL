import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("knowledge base card styles", () => {
  it("keeps knowledge base asset cards visually substantial", () => {
    const css = readFileSync(resolve(__dirname, "../src/styles/global.css"), "utf8");

    expect(css).toContain("grid-template-columns: repeat(auto-fill, minmax(520px, 1fr));");
    expect(css).toContain("min-height: 320px;");
    expect(css).toContain(".kb-card-grid {\n    grid-template-columns: 1fr;\n  }");
  });
});
