import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const ROOT = process.cwd();
const SRC_DIR = join(ROOT, "src");
const GENERATED_DIR = join(SRC_DIR, "generated");

async function readAsset(...parts) {
  return await readFile(join(SRC_DIR, ...parts), "utf8");
}

function tsString(value) {
  return JSON.stringify(value);
}

async function main() {
  const help = await readAsset("help.txt");
  const bash = await readAsset("completions", "bash.txt");
  const zsh = await readAsset("completions", "zsh.txt");
  const fish = await readAsset("completions", "fish.txt");

  await mkdir(GENERATED_DIR, { recursive: true });

  await writeFile(
    join(GENERATED_DIR, "help.ts"),
    `export const HELP_TEXT = ${tsString(help)};\n`,
    "utf8",
  );

  await writeFile(
    join(GENERATED_DIR, "completions.ts"),
    [
      `export function renderBashCompletion(): string {`,
      `  return ${tsString(bash)};`,
      `}`,
      ``,
      `export function renderZshCompletion(): string {`,
      `  return ${tsString(zsh)};`,
      `}`,
      ``,
      `export function renderFishCompletion(): string {`,
      `  return ${tsString(fish)};`,
      `}`,
      ``,
    ].join("\n"),
    "utf8",
  );
}

await main();
