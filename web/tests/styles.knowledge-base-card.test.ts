import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("knowledge base card styles", () => {
  it("does not keep migrated knowledge base card styles in global CSS", () => {
    const css = readFileSync(resolve(__dirname, "../src/styles/global.css"), "utf8");

    expect(css).not.toContain(".kb-card");
    expect(css).not.toContain(".kb-card-grid");
    expect(css).not.toContain(".settings-dialog");
  });
});
