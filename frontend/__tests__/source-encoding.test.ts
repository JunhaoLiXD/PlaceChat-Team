import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, test } from "vitest";

// UTF-8 text such as … or ’ that was decoded as Windows-1252 and saved again
// shows up as "â€¦" or "â€™" on the page. Catch it before it ships.
const MOJIBAKE = /â€|Ã[\u0080-¿]/;
const SOURCE_DIR = join(__dirname, "..", "src");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx|css)$/.test(name) ? [path] : [];
  });
}

describe("source encoding", () => {
  test("no garbled UTF-8 text in src", () => {
    const garbled = sourceFiles(SOURCE_DIR).flatMap((file) =>
      readFileSync(file, "utf8")
        .split("\n")
        .flatMap((line, index) =>
          MOJIBAKE.test(line)
            ? [`${relative(SOURCE_DIR, file)}:${index + 1}`]
            : [],
        ),
    );

    expect(garbled).toEqual([]);
  });
});
