#!/usr/bin/env bun
/* eslint-disable no-console */

import { mkdir } from "node:fs/promises";
import { homedir, platform } from "node:os";
import { dirname, join } from "node:path";

type Provider = "github" | "gitignoreio";
type SourceName = "github" | "github-global" | "github-community" | "gitignoreio" | "all";
type DetectInclude = "os" | "editor";
type GitHubScope = "all" | "root" | "global" | "community";

type Args = {
  command?: string;
  rest: string[];
  output: string;
  force: boolean;
  source: SourceName;
  noCache: boolean;
  noComments: boolean;
  detectIncludes: DetectInclude[];
};

type GitHubTreeItem = {
  path: string;
  type: string;
};

type GitHubTreeResponse = {
  tree: GitHubTreeItem[];
};

type CatalogEntry = {
  source: Provider;
  name: string;
  key: string;
  displayName: string;
  aliases: string[];
  githubScope?: Exclude<GitHubScope, "all">;
};

type DetectRule = {
  check: () => Promise<boolean>;
  github?: string[];
  gitignoreio?: string[];
};

type ParsedTemplateRef = {
  provider?: Provider;
  githubScope?: GitHubScope;
  name: string;
};

type DoctorCheck = {
  name: string;
  ok: boolean;
  detail: string;
};

type StatsRow = {
  label: string;
  count: number;
};

const GITHUB_API_BASE = "https://api.github.com";
const GITHUB_REPO = "github/gitignore";
const GITHUB_BRANCH = "main";
const GITHUB_TREE_URL = `${GITHUB_API_BASE}/repos/${GITHUB_REPO}/git/trees/${GITHUB_BRANCH}?recursive=1`;
const GITHUB_RAW_BASE = `https://raw.githubusercontent.com/${GITHUB_REPO}/${GITHUB_BRANCH}`;
const GITIGNORE_IO_BASE = "https://www.toptal.com/developers/gitignore/api";

const CACHE_DIR = join(homedir(), ".cache", "gitig");
const CACHE_TTL_MS = 1000 * 60 * 60 * 24;

const COMMANDS = ["list", "search", "view", "init", "I", "i", "detect", "compact", "doctor", "stats", "completion", "install-completion", "help"] as const;

const SOURCE_ALIASES = {
  gh: "github",
  ghg: "github-global",
  ghc: "github-community",
  tt: "gitignoreio",
} as const;

const DETECT_INCLUDE_VALUES = ["os", "editor"] as const;

function printHelp(): void {
  console.log(
    `
gitig

Usage:
    gitig list [--source github|gh|ghg|ghc|gitignoreio|tt|all]
    gitig search <query> [--source github|gh|ghg|ghc|gitignoreio|tt|all]
    gitig view <template> [--source github|gh|ghg|ghc|gitignoreio|tt] [--no-comments|-nc]
    gitig init <template[,template...]|template ...> [--source github|gh|ghg|ghc|gitignoreio|tt] [--output .gitignore] [--force] [--no-comments|-nc]
    gitig I <template[,template...]|template ...> [--source github|gh|ghg|ghc|gitignoreio|tt] [--output .gitignore] [--force] [--no-comments|-nc]
    gitig i <template[,template...]|template ...> [--source github|gh|ghg|ghc|gitignoreio|tt] [--output .gitignore] [--force] [--no-comments|-nc]
    gitig detect [--source github|gh|ghg|gitignoreio|tt] [--include os,editor] [--output .gitignore] [--force] [--no-comments|-nc]
    gitig compact [input] [--output file] [--force]
    gitig doctor
    gitig stats [--source github|gh|ghg|ghc|gitignoreio|tt|all]
    gitig completion <bash|zsh|fish>
    gitig install-completion <bash|zsh|fish>

Source aliases:
    gh   = all GitHub templates
    ghg  = GitHub Global/ templates
    ghc  = GitHub community/ templates
    tt   = gitignore.io

Examples:
    gitig view gh:Node -nc
    gitig init gh:Node,ghg:macOS -nc --force
    gitig init gh:Node ghg:macOS -nc --force
    gitig I gh:Node ghg:macOS
    gitig i gh:node ghg:macos
    gitig i gh: node python
    gitig i ghg: macos jetbrains
    gitig i tt: node macos vscode

    gitig detect --source gh --include os,editor -nc --force

    gitig compact
    gitig compact .gitignore
    gitig compact .gitignore --output .gitignore.clean --force

    gitig stats
    gitig stats --source gh

Notes:
    - ghg uses names relative to Global/, so ghg:macOS resolves to Global/macOS
    - ghc uses names relative to community/, so ghc:Python/Poetry resolves to community/Python/Poetry
    - template matching is case-insensitive
    - provider prefixes can be sticky, so "gh: node python" means "gh:node gh:python"
    - --no-comments (-nc) removes full-line comments and empty lines
    - compact removes comments from an existing .gitignore-like file
`.trim(),
  );
}

function normalizeText(value: string): string {
  return value.trim().replace(/\\/g, "/");
}

function normalizeLoose(value: string): string {
  return normalizeText(value)
    .replace(/\.gitignore$/i, "")
    .replace(/[\s_\-]+/g, "")
    .replace(/\//g, "")
    .replace(/:/g, "")
    .toLowerCase();
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}

function normalizeSourceName(value: string): SourceName {
  const normalized = value.trim().toLowerCase();

  if (normalized === "all") {
    return "all";
  }

  if (normalized === "github" || normalized === "github-global" || normalized === "github-community" || normalized === "gitignoreio") {
    return normalized;
  }

  if (normalized in SOURCE_ALIASES) {
    return SOURCE_ALIASES[normalized as keyof typeof SOURCE_ALIASES];
  }

  throw new Error("Invalid value for --source. Use github, gh, ghg, ghc, gitignoreio, tt, or all.");
}

function sourceToGitHubScope(source: SourceName): GitHubScope | null {
  switch (source) {
    case "github":
      return "all";
    case "github-global":
      return "global";
    case "github-community":
      return "community";
    default:
      return null;
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": "gitig",
    },
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

async function fetchText(url: string): Promise<string> {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "gitig",
    },
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }

  return await response.text();
}

function parseDetectIncludes(value: string): DetectInclude[] {
  const parts = value
    .split(",")
    .map((part) => part.trim().toLowerCase())
    .filter((part) => part.length > 0);

  const invalid = parts.filter((part): part is string => !DETECT_INCLUDE_VALUES.includes(part as DetectInclude));

  if (invalid.length > 0) {
    throw new Error(`Invalid value for --include: ${invalid.join(", ")}`);
  }

  return [...new Set(parts as DetectInclude[])];
}

function parseArgs(argv: string[]): Args {
  const args = [...argv];
  let output = ".gitignore";
  let force = false;
  let source: SourceName | undefined;
  let noCache = false;
  let noComments = false;
  let detectIncludes: DetectInclude[] = [];
  const filtered: string[] = [];

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];

    if (arg === "--output" || arg === "-o") {
      const next = args[i + 1];
      if (typeof next !== "string" || next.length === 0) {
        throw new Error("Missing value for --output");
      }
      output = next;
      i += 1;
      continue;
    }

    if (arg === "--force" || arg === "-f") {
      force = true;
      continue;
    }

    if (arg === "--source" || arg === "-s") {
      const next = args[i + 1];
      if (typeof next !== "string" || next.length === 0) {
        throw new Error("Missing value for --source");
      }
      source = normalizeSourceName(next);
      i += 1;
      continue;
    }

    if (arg === "--include") {
      const next = args[i + 1];
      if (typeof next !== "string" || next.length === 0) {
        throw new Error("Missing value for --include");
      }
      detectIncludes = parseDetectIncludes(next);
      i += 1;
      continue;
    }

    if (arg === "--no-cache") {
      noCache = true;
      continue;
    }

    if (arg === "--no-comments" || arg === "-nc") {
      noComments = true;
      continue;
    }

    filtered.push(arg);
  }

  const command = filtered.length > 0 ? filtered[0] : undefined;
  const rest = filtered.slice(1);

  return {
    command,
    rest,
    output,
    force,
    source: source ?? defaultSourceForCommand(command),
    noCache,
    noComments,
    detectIncludes,
  };
}

function defaultSourceForCommand(command?: string): SourceName {
  switch (command) {
    case "list":
    case "search":
    case "stats":
      return "all";
    case "view":
    case "init":
    case "I":
    case "i":
    case "detect":
      return "github";
    default:
      return "all";
  }
}

function assertSingleSource(source: SourceName, command: string): Exclude<SourceName, "all"> {
  if (source === "all") {
    throw new Error(`${command} requires --source github/gh/ghg/ghc or gitignoreio/tt`);
  }

  return source;
}

async function ensureDir(path: string): Promise<void> {
  await mkdir(path, { recursive: true });
}

async function ensureCacheDir(): Promise<void> {
  await ensureDir(CACHE_DIR);
}

async function readCacheJson<T>(path: string): Promise<T | null> {
  try {
    const file = Bun.file(path);
    if (!(await file.exists())) {
      return null;
    }

    const stat = await file.stat();
    const ageMs = Date.now() - stat.mtime.getTime();

    if (ageMs > CACHE_TTL_MS) {
      return null;
    }

    return JSON.parse(await file.text()) as T;
  } catch {
    return null;
  }
}

async function writeCacheJson(path: string, value: unknown): Promise<void> {
  await ensureCacheDir();
  await Bun.write(path, JSON.stringify(value, null, 2));
}

function cachePathFor(name: string): string {
  return join(CACHE_DIR, `${name}.json`);
}

function classifyGitHubTemplate(path: string): CatalogEntry | null {
  if (!path.endsWith(".gitignore")) {
    return null;
  }

  if (path.startsWith("Global/")) {
    const relative = path.slice("Global/".length).replace(/\.gitignore$/i, "");
    const full = path.replace(/\.gitignore$/i, "");
    return {
      source: "github",
      name: full,
      key: path,
      displayName: full,
      aliases: uniqueSorted([full, relative, `${relative}.gitignore`, `Global/${relative}`, `ghg:${relative}`, `github-global:${relative}`]),
      githubScope: "global",
    };
  }

  if (path.startsWith("community/")) {
    const relative = path.slice("community/".length).replace(/\.gitignore$/i, "");
    const full = path.replace(/\.gitignore$/i, "");
    return {
      source: "github",
      name: full,
      key: path,
      displayName: full,
      aliases: uniqueSorted([full, relative, `${relative}.gitignore`, `community/${relative}`, `ghc:${relative}`, `github-community:${relative}`]),
      githubScope: "community",
    };
  }

  if (path.includes("/")) {
    return null;
  }

  const name = path.replace(/\.gitignore$/i, "");
  return {
    source: "github",
    name,
    key: path,
    displayName: name,
    aliases: uniqueSorted([name, `${name}.gitignore`, `gh:${name}`, `github:${name}`]),
    githubScope: "root",
  };
}

async function getGitHubCatalog(noCache: boolean): Promise<CatalogEntry[]> {
  const cachePath = cachePathFor("github-catalog");

  if (!noCache) {
    const cached = await readCacheJson<CatalogEntry[]>(cachePath);
    if (cached !== null) {
      return cached;
    }
  }

  const tree = await fetchJson<GitHubTreeResponse>(GITHUB_TREE_URL);

  const catalog = tree.tree
    .filter((item) => item.type === "blob")
    .map((item) => classifyGitHubTemplate(item.path))
    .filter((item): item is CatalogEntry => item !== null)
    .sort((a, b) => a.displayName.localeCompare(b.displayName));

  if (!noCache) {
    await writeCacheJson(cachePath, catalog);
  }

  return catalog;
}

async function getGitignoreIoCatalog(noCache: boolean): Promise<CatalogEntry[]> {
  const cachePath = cachePathFor("gitignoreio-catalog");

  if (!noCache) {
    const cached = await readCacheJson<CatalogEntry[]>(cachePath);
    if (cached !== null) {
      return cached;
    }
  }

  const text = await fetchText(`${GITIGNORE_IO_BASE}/list`);
  const keys = text
    .split(/[,\n]/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);

  const catalog = uniqueSorted(keys).map((key) => ({
    source: "gitignoreio" as const,
    name: key,
    key,
    displayName: key,
    aliases: uniqueSorted([key, `tt:${key}`, `gitignoreio:${key}`]),
  }));

  if (!noCache) {
    await writeCacheJson(cachePath, catalog);
  }

  return catalog;
}

function filterGitHubCatalogByScope(catalog: CatalogEntry[], scope: GitHubScope): CatalogEntry[] {
  if (scope === "all") {
    return catalog;
  }

  if (scope === "root") {
    return catalog.filter((entry) => entry.githubScope === "root");
  }

  if (scope === "global") {
    return catalog.filter((entry) => entry.githubScope === "global");
  }

  return catalog.filter((entry) => entry.githubScope === "community");
}

async function getCatalog(source: SourceName, noCache: boolean): Promise<CatalogEntry[]> {
  if (source === "github" || source === "github-global" || source === "github-community") {
    const github = await getGitHubCatalog(noCache);
    const scope = sourceToGitHubScope(source);
    return scope === null ? github : filterGitHubCatalogByScope(github, scope);
  }

  if (source === "gitignoreio") {
    return await getGitignoreIoCatalog(noCache);
  }

  const [github, gitignoreio] = await Promise.all([getGitHubCatalog(noCache), getGitignoreIoCatalog(noCache)]);

  return [...github, ...gitignoreio].sort((a, b) => {
    const byName = a.displayName.localeCompare(b.displayName);
    if (byName !== 0) {
      return byName;
    }
    return a.source.localeCompare(b.source);
  });
}

function parseProviderPrefix(value: string): ParsedTemplateRef {
  const trimmed = normalizeText(value);
  const match = /^([a-z-]+):(.*)$/i.exec(trimmed);

  if (match === null) {
    return { name: trimmed };
  }

  const rawProvider = match[1].toLowerCase();
  const rawName = match[2].trim();

  if (rawProvider === "github" || rawProvider === "gh") {
    return {
      provider: "github",
      githubScope: "all",
      name: rawName,
    };
  }

  if (rawProvider === "ghg" || rawProvider === "github-global") {
    return {
      provider: "github",
      githubScope: "global",
      name: rawName,
    };
  }

  if (rawProvider === "ghc" || rawProvider === "github-community") {
    return {
      provider: "github",
      githubScope: "community",
      name: rawName,
    };
  }

  if (rawProvider === "gitignoreio" || rawProvider === "tt") {
    return {
      provider: "gitignoreio",
      name: rawName,
    };
  }

  return { name: trimmed };
}

function normalizeScopedGitHubName(name: string, scope: GitHubScope): string {
  const normalized = normalizeText(name).replace(/\.gitignore$/i, "");

  if (scope === "global") {
    if (normalized.startsWith("Global/")) {
      return normalized;
    }
    return `Global/${normalized}`;
  }

  if (scope === "community") {
    if (normalized.startsWith("community/")) {
      return normalized;
    }
    return `community/${normalized}`;
  }

  return normalized;
}

function resolveEntry(name: string, catalog: CatalogEntry[]): CatalogEntry | null {
  const parsed = parseProviderPrefix(name);
  let scopedCatalog = catalog;

  if (parsed.provider !== undefined) {
    scopedCatalog = scopedCatalog.filter((entry) => entry.source === parsed.provider);
  }

  if (parsed.provider === "github" && parsed.githubScope !== undefined) {
    scopedCatalog = filterGitHubCatalogByScope(scopedCatalog, parsed.githubScope);
  }

  const raw = normalizeText(parsed.name);
  const loose = normalizeLoose(parsed.name);

  const candidateNames: string[] = [raw];

  if (parsed.provider === "github" && parsed.githubScope !== undefined) {
    candidateNames.push(normalizeScopedGitHubName(parsed.name, parsed.githubScope));
  }

  for (const candidate of candidateNames) {
    const exact = scopedCatalog.find((entry) => entry.displayName === candidate);
    if (exact !== undefined) {
      return exact;
    }
  }

  for (const candidate of candidateNames) {
    const lower = candidate.toLowerCase();
    const match = scopedCatalog.find((entry) => entry.displayName.toLowerCase() === lower);
    if (match !== undefined) {
      return match;
    }
  }

  for (const entry of scopedCatalog) {
    const aliasMatch = entry.aliases.find((alias) => alias.toLowerCase() === raw.toLowerCase());
    if (aliasMatch !== undefined) {
      return entry;
    }
  }

  for (const entry of scopedCatalog) {
    if (normalizeLoose(entry.displayName) === loose) {
      return entry;
    }

    const aliasMatch = entry.aliases.find((alias) => normalizeLoose(alias) === loose);
    if (aliasMatch !== undefined) {
      return entry;
    }
  }

  return null;
}

function levenshtein(a: string, b: string): number {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const dp: number[][] = Array.from({ length: rows }, () => Array<number>(cols).fill(0));

  for (let i = 0; i < rows; i += 1) {
    dp[i][0] = i;
  }

  for (let j = 0; j < cols; j += 1) {
    dp[0][j] = j;
  }

  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost);
    }
  }

  return dp[a.length][b.length];
}

function getSuggestions(query: string, catalog: CatalogEntry[], limit = 5): CatalogEntry[] {
  const parsed = parseProviderPrefix(query);
  let scopedCatalog = catalog;

  if (parsed.provider !== undefined) {
    scopedCatalog = scopedCatalog.filter((entry) => entry.source === parsed.provider);
  }

  if (parsed.provider === "github" && parsed.githubScope !== undefined) {
    scopedCatalog = filterGitHubCatalogByScope(scopedCatalog, parsed.githubScope);
  }

  const normalizedQuery = normalizeLoose(parsed.name);

  const ranked = scopedCatalog
    .map((entry) => {
      const candidates = [entry.displayName, ...entry.aliases];
      const scores = candidates.map((candidate) => {
        const normalizedCandidate = normalizeLoose(candidate);

        if (normalizedCandidate.includes(normalizedQuery) || normalizedQuery.includes(normalizedCandidate)) {
          return 0;
        }

        return levenshtein(normalizedQuery, normalizedCandidate);
      });

      return {
        entry,
        score: Math.min(...scores),
      };
    })
    .sort((a, b) => {
      if (a.score !== b.score) {
        return a.score - b.score;
      }
      return a.entry.displayName.localeCompare(b.entry.displayName);
    });

  return ranked.slice(0, limit).map((item) => item.entry);
}

function formatSuggestionPrefix(entry: CatalogEntry): string {
  if (entry.source === "gitignoreio") {
    return "tt";
  }

  if (entry.githubScope === "global") {
    return "ghg";
  }

  if (entry.githubScope === "community") {
    return "ghc";
  }

  return "gh";
}

function formatSuggestions(query: string, catalog: CatalogEntry[]): string {
  const suggestions = getSuggestions(query, catalog);

  if (suggestions.length === 0) {
    return "";
  }

  const lines = suggestions.map((entry) => {
    const prefix = formatSuggestionPrefix(entry);
    const suggestedName = entry.githubScope === "global" ? entry.displayName.replace(/^Global\//, "") : entry.githubScope === "community" ? entry.displayName.replace(/^community\//, "") : entry.displayName;

    return `  - ${prefix}:${suggestedName}`;
  });

  return `Did you mean:\n${lines.join("\n")}`;
}

async function getGitHubTemplateContent(path: string): Promise<string> {
  return await fetchText(`${GITHUB_RAW_BASE}/${path}`);
}

async function getGitignoreIoTemplateContent(keys: string[]): Promise<string> {
  const joined = keys
    .map((key) => key.trim())
    .filter((key) => key.length > 0)
    .join(",");

  if (joined.length === 0) {
    throw new Error("Please provide at least one gitignore.io template");
  }

  return await fetchText(`${GITIGNORE_IO_BASE}/${encodeURIComponent(joined)}`);
}

function stripCommentLines(content: string): string {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const kept: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.length === 0) {
      continue;
    }

    if (trimmed.startsWith("#") && !trimmed.startsWith("\\#")) {
      continue;
    }

    kept.push(line);
  }

  return kept.join("\n").replace(/\n*$/, "\n");
}

function applyNoComments(content: string, noComments: boolean): string {
  return noComments ? stripCommentLines(content) : content;
}

function dedupeLines(content: string): string {
  const seen = new Set<string>();
  const output: string[] = [];

  for (const line of content.replace(/\r\n/g, "\n").split("\n")) {
    if (seen.has(line)) {
      continue;
    }
    seen.add(line);
    output.push(line);
  }

  return `${output.join("\n").replace(/\n*$/, "\n")}`;
}

function displayNameForSource(entry: CatalogEntry, source: SourceName): string {
  if (source === "github-global") {
    return entry.displayName.replace(/^Global\//, "");
  }

  if (source === "github-community") {
    return entry.displayName.replace(/^community\//, "");
  }

  return entry.displayName;
}

async function pathExists(path: string): Promise<boolean> {
  return await Bun.file(path).exists();
}

async function getDetectedExtras(provider: Provider, includes: DetectInclude[]): Promise<string[]> {
  const values = new Set<string>();

  if (includes.includes("os")) {
    if (provider === "github") {
      if (platform() === "darwin") {
        values.add("Global/macOS");
      } else if (platform() === "win32") {
        values.add("Global/Windows");
      } else {
        values.add("Global/Linux");
      }
    } else {
      if (platform() === "darwin") {
        values.add("macos");
      } else if (platform() === "win32") {
        values.add("windows");
      } else {
        values.add("linux");
      }
    }
  }

  if (includes.includes("editor")) {
    const hasVscode = (await pathExists(".vscode")) || (await pathExists(".vscode/settings.json"));
    const hasIdea = await pathExists(".idea");
    const hasVs = await pathExists(".vs");

    if (provider === "github") {
      if (hasIdea) {
        values.add("Global/JetBrains");
      } else if (hasVs) {
        values.add("Global/VisualStudio");
      } else {
        values.add("Global/VisualStudioCode");
      }
    } else {
      if (hasIdea) {
        values.add("jetbrains");
      } else if (hasVs) {
        values.add("visualstudio");
      } else {
        values.add("vscode");
      }
    }
  }

  return [...values];
}

async function detectTemplates(source: Exclude<SourceName, "all">, includes: DetectInclude[]): Promise<string[]> {
  const provider: Provider = source === "gitignoreio" ? "gitignoreio" : "github";

  const rules: DetectRule[] = [
    {
      check: async () => await pathExists("package.json"),
      github: ["Node"],
      gitignoreio: ["node"],
    },
    {
      check: async () => await pathExists("bun.lock"),
      github: ["Node"],
      gitignoreio: ["node"],
    },
    {
      check: async () => await pathExists("bun.lockb"),
      github: ["Node"],
      gitignoreio: ["node"],
    },
    {
      check: async () => await pathExists("pnpm-lock.yaml"),
      github: ["Node"],
      gitignoreio: ["node"],
    },
    {
      check: async () => await pathExists("yarn.lock"),
      github: ["Node"],
      gitignoreio: ["node"],
    },
    {
      check: async () => await pathExists("package-lock.json"),
      github: ["Node"],
      gitignoreio: ["node"],
    },
    {
      check: async () => await pathExists("Cargo.toml"),
      github: ["Rust"],
      gitignoreio: ["rust"],
    },
    {
      check: async () => await pathExists("go.mod"),
      github: ["Go"],
      gitignoreio: ["go"],
    },
    {
      check: async () => await pathExists("pyproject.toml"),
      github: ["Python"],
      gitignoreio: ["python"],
    },
    {
      check: async () => await pathExists("requirements.txt"),
      github: ["Python"],
      gitignoreio: ["python"],
    },
    {
      check: async () => await pathExists("Pipfile"),
      github: ["Python"],
      gitignoreio: ["python"],
    },
    {
      check: async () => await pathExists(".venv"),
      github: ["Python"],
      gitignoreio: ["python"],
    },
  ];

  const found = new Set<string>();

  for (const rule of rules) {
    if (await rule.check()) {
      const templates = provider === "github" ? rule.github : rule.gitignoreio;
      if (templates !== undefined) {
        for (const template of templates) {
          found.add(template);
        }
      }
    }
  }

  for (const extra of await getDetectedExtras(provider, includes)) {
    found.add(extra);
  }

  if (provider === "github") {
    const scope = sourceToGitHubScope(source);
    if (scope === "global") {
      return [...found].filter((name) => name.startsWith("Global/")).map((name) => name.replace(/^Global\//, ""));
    }
    if (scope === "community") {
      return [...found].filter((name) => name.startsWith("community/")).map((name) => name.replace(/^community\//, ""));
    }
  }

  return [...found];
}

function parseTemplateArgs(parts: string[]): string[] {
  const tokens = parts
    .flatMap((part) => part.split(","))
    .map((part) => part.trim())
    .filter((part) => part.length > 0);

  const expanded: string[] = [];
  let stickyPrefix = "";

  for (const token of tokens) {
    const normalized = normalizeText(token);

    if (normalized.endsWith(":")) {
      stickyPrefix = normalized;
      continue;
    }

    const parsed = parseProviderPrefix(normalized);
    if (parsed.provider !== undefined) {
      expanded.push(normalized);
      const colonIndex = normalized.indexOf(":");
      if (colonIndex >= 0) {
        stickyPrefix = normalized.slice(0, colonIndex + 1);
      }
      continue;
    }

    if (stickyPrefix.length > 0) {
      expanded.push(`${stickyPrefix}${normalized}`);
    } else {
      expanded.push(normalized);
    }
  }

  return expanded;
}

async function cmdList(source: SourceName, noCache: boolean): Promise<void> {
  const catalog = await getCatalog(source, noCache);

  for (const entry of catalog) {
    if (source === "all") {
      console.log(`${entry.displayName}\t[${entry.source}]`);
    } else {
      console.log(displayNameForSource(entry, source));
    }
  }
}

async function cmdSearch(query: string, source: SourceName, noCache: boolean): Promise<void> {
  const q = query.trim();
  if (q.length === 0) {
    throw new Error("Please provide a search query");
  }

  const qLoose = normalizeLoose(q);
  const catalog = await getCatalog(source, noCache);

  const matches = catalog.filter((entry) => {
    if (normalizeLoose(entry.displayName).includes(qLoose)) {
      return true;
    }

    return entry.aliases.some((alias) => normalizeLoose(alias).includes(qLoose));
  });

  if (matches.length === 0) {
    console.error(`No templates found for "${query}"`);
    const suggestions = formatSuggestions(query, catalog);
    if (suggestions.length > 0) {
      console.error(suggestions);
    }
    process.exit(1);
  }

  for (const entry of matches) {
    if (source === "all") {
      console.log(`${entry.displayName}\t[${entry.source}]`);
    } else {
      console.log(displayNameForSource(entry, source));
    }
  }
}

async function cmdView(name: string, source: SourceName, noCache: boolean, noComments: boolean): Promise<void> {
  const parsed = parseProviderPrefix(name);
  const effectiveSource: Exclude<SourceName, "all"> = parsed.provider !== undefined ? (parsed.provider === "gitignoreio" ? "gitignoreio" : parsed.githubScope === "global" ? "github-global" : parsed.githubScope === "community" ? "github-community" : "github") : assertSingleSource(source, "view");

  const catalog = await getCatalog(effectiveSource, noCache);
  const entry = resolveEntry(name, catalog);

  if (entry === null) {
    console.error(`Template not found: ${name}`);
    const suggestions = formatSuggestions(name, catalog);
    if (suggestions.length > 0) {
      console.error(suggestions);
    }
    process.exit(1);
  }

  let content = "";

  if (entry.source === "github") {
    content = await getGitHubTemplateContent(entry.key);
  } else {
    content = await getGitignoreIoTemplateContent([entry.key]);
  }

  content = applyNoComments(content, noComments);
  process.stdout.write(content.endsWith("\n") ? content : `${content}\n`);
}

async function cmdInit(rawNames: string[], source: SourceName, output: string, force: boolean, noCache: boolean, noComments: boolean): Promise<void> {
  const requestedNames = parseTemplateArgs(rawNames);

  if (requestedNames.length === 0) {
    throw new Error("Please provide at least one template name");
  }

  const target = Bun.file(output);
  if ((await target.exists()) && !force) {
    console.error(`${output} already exists. Use --force to overwrite.`);
    process.exit(1);
  }

  const effectiveSources = uniqueSorted(
    requestedNames.map((requestedName) => {
      const parsed = parseProviderPrefix(requestedName);

      if (parsed.provider === undefined) {
        return assertSingleSource(source, "init");
      }

      if (parsed.provider === "gitignoreio") {
        return "gitignoreio";
      }

      if (parsed.githubScope === "global") {
        return "github-global";
      }

      if (parsed.githubScope === "community") {
        return "github-community";
      }

      return "github";
    }),
  );

  const hasGitHub = effectiveSources.some((item) => item.startsWith("github"));
  const hasGitignoreIo = effectiveSources.includes("gitignoreio");

  if (hasGitHub && hasGitignoreIo) {
    throw new Error("init cannot mix GitHub templates and gitignore.io templates in one command");
  }

  const effectiveSource = effectiveSources[0];
  if (effectiveSource === undefined) {
    throw new Error("Could not determine source for init");
  }

  const catalog = await getCatalog(effectiveSource as SourceName, noCache);
  const resolved: CatalogEntry[] = [];

  for (const requestedName of requestedNames) {
    const entry = resolveEntry(requestedName, catalog);
    if (entry === null) {
      console.error(`Template not found: ${requestedName}`);
      const suggestions = formatSuggestions(requestedName, catalog);
      if (suggestions.length > 0) {
        console.error(suggestions);
      }
      process.exit(1);
    }
    resolved.push(entry);
  }

  let content = "";

  if (resolved[0]?.source === "github") {
    const parts: string[] = [];

    for (const entry of resolved) {
      const section = await getGitHubTemplateContent(entry.key);
      const cleanedSection = applyNoComments(section, noComments).trimEnd();

      if (cleanedSection.length === 0) {
        continue;
      }

      if (noComments) {
        parts.push(cleanedSection);
      } else {
        parts.push(`# --- ${entry.displayName} ---\n${cleanedSection}`);
      }
    }

    content = `${parts.join("\n\n")}\n`;
  } else {
    const keys = resolved.map((entry) => entry.key);
    const generated = await getGitignoreIoTemplateContent(keys);
    content = applyNoComments(dedupeLines(generated), noComments);
  }

  await Bun.write(output, content);
  console.log(`Wrote ${output}`);
}

async function cmdDetect(source: SourceName, output: string, force: boolean, noCache: boolean, includes: DetectInclude[], noComments: boolean): Promise<void> {
  const effectiveSource = assertSingleSource(source, "detect");

  if (effectiveSource === "github-community") {
    throw new Error("detect does not support ghc/github-community");
  }

  const detected = await detectTemplates(effectiveSource, includes);

  if (detected.length === 0) {
    console.error("Could not detect any matching project templates in the current directory.");
    process.exit(1);
  }

  console.log(`Detected templates: ${detected.join(", ")}`);
  await cmdInit(detected, effectiveSource, output, force, noCache, noComments);
}

async function cmdCompact(inputPath: string | undefined, outputPath: string, force: boolean): Promise<void> {
  const input = inputPath?.trim().length ? inputPath : ".gitignore";
  const inputFile = Bun.file(input);

  if (!(await inputFile.exists())) {
    throw new Error(`Input file not found: ${input}`);
  }

  const sameTarget = input === outputPath;
  const outputFile = Bun.file(outputPath);

  if (!sameTarget && (await outputFile.exists()) && !force) {
    console.error(`${outputPath} already exists. Use --force to overwrite.`);
    process.exit(1);
  }

  const original = await inputFile.text();
  const compacted = stripCommentLines(original);

  await Bun.write(outputPath, compacted);
  console.log(`Wrote ${outputPath}`);
}

function renderBashCompletion(): string {
  return String.raw`_gitig_completion() {
    local cur prev words cword
    _init_completion || return

    local commands="list search view init I i detect compact doctor stats completion install-completion help"
    local sources="github gh ghg ghc gitignoreio tt all"
    local detect_sources="github gh ghg gitignoreio tt"
    local include_values="os editor os,editor"
    local shells="bash zsh fish"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return
    fi

    case "${words[1]}" in
        completion|install-completion)
            COMPREPLY=( $(compgen -W "$shells" -- "$cur") )
            return
            ;;
        list|search|stats)
            if [[ "$prev" == "--source" || "$prev" == "-s" ]]; then
                COMPREPLY=( $(compgen -W "$sources" -- "$cur") )
                return
            fi
            COMPREPLY=( $(compgen -W "--source -s --no-cache" -- "$cur") )
            return
            ;;
        detect)
            if [[ "$prev" == "--source" || "$prev" == "-s" ]]; then
                COMPREPLY=( $(compgen -W "$detect_sources" -- "$cur") )
                return
            fi
            if [[ "$prev" == "--include" ]]; then
                COMPREPLY=( $(compgen -W "$include_values" -- "$cur") )
                return
            fi
            COMPREPLY=( $(compgen -W "--source -s --include --output -o --force -f --no-cache --no-comments -nc" -- "$cur") )
            return
            ;;
        compact)
            COMPREPLY=( $(compgen -W "--output -o --force -f" -- "$cur") )
            return
            ;;
        doctor)
            COMPREPLY=( $(compgen -W "--no-cache" -- "$cur") )
            return
            ;;
        view|init|I|i)
            if [[ "$prev" == "--source" || "$prev" == "-s" ]]; then
                COMPREPLY=( $(compgen -W "github gh ghg ghc gitignoreio tt" -- "$cur") )
                return
            fi

            if [[ "$cur" == --* ]]; then
                COMPREPLY=( $(compgen -W "--source -s --output -o --force -f --no-cache --no-comments -nc" -- "$cur") )
                return
            fi
            ;;
    esac
}

complete -F _gitig_completion gitig
`;
}

function renderZshCompletion(): string {
  return String.raw`#compdef gitig

_gitig() {
    _arguments -C \
        '1:command:(list search view init I i detect compact doctor stats completion install-completion help)' \
        '--source[template source]:source:(github gh ghg ghc gitignoreio tt all)' \
        '--include[extra detect categories]:include:(os editor os,editor)' \
        '--output[output file]:file:_files' \
        '--force[overwrite output file]' \
        '--no-cache[disable catalog cache]' \
        '--no-comments[strip full-line comments and empty lines]' \
        '-nc[strip full-line comments and empty lines]' \
        '*::arg:_files'
}

_gitig "$@"
`;
}

function renderFishCompletion(): string {
  return String.raw`complete -c gitig -f
complete -c gitig -n "__fish_use_subcommand" -a "list search view init I i detect compact doctor stats completion install-completion help"
complete -c gitig -n "__fish_seen_subcommand_from completion install-completion" -a "bash zsh fish"
complete -c gitig -n "__fish_seen_subcommand_from list search stats" -l source -s s -a "github gh ghg ghc gitignoreio tt all"
complete -c gitig -n "__fish_seen_subcommand_from detect" -l source -s s -a "github gh ghg gitignoreio tt"
complete -c gitig -n "__fish_seen_subcommand_from detect" -l include -a "os editor os,editor"
complete -c gitig -n "__fish_seen_subcommand_from detect" -l output -s o -r
complete -c gitig -n "__fish_seen_subcommand_from detect" -l force -s f
complete -c gitig -n "__fish_seen_subcommand_from detect" -l no-cache
complete -c gitig -n "__fish_seen_subcommand_from detect" -l no-comments
complete -c gitig -n "__fish_seen_subcommand_from detect" -s nc
complete -c gitig -n "__fish_seen_subcommand_from compact" -l output -s o -r
complete -c gitig -n "__fish_seen_subcommand_from compact" -l force -s f
complete -c gitig -n "__fish_seen_subcommand_from doctor" -l no-cache
complete -c gitig -n "__fish_seen_subcommand_from view init I i" -l source -s s -a "github gh ghg ghc gitignoreio tt"
complete -c gitig -n "__fish_seen_subcommand_from view init I i" -l output -s o -r
complete -c gitig -n "__fish_seen_subcommand_from view init I i" -l force -s f
complete -c gitig -n "__fish_seen_subcommand_from view init I i" -l no-cache
complete -c gitig -n "__fish_seen_subcommand_from view init I i" -l no-comments
complete -c gitig -n "__fish_seen_subcommand_from view init I i" -s nc
`;
}

function cmdCompletion(shellName: string): void {
  switch (shellName) {
    case "bash":
      process.stdout.write(renderBashCompletion());
      return;
    case "zsh":
      process.stdout.write(renderZshCompletion());
      return;
    case "fish":
      process.stdout.write(renderFishCompletion());
      return;
    default:
      throw new Error("completion requires one of: bash, zsh, fish");
  }
}

function getCompletionInstallTarget(shellName: string): {
  path: string;
  content: string;
  note: string;
} {
  switch (shellName) {
    case "bash":
      return {
        path: join(homedir(), ".gitig-completion.bash"),
        content: renderBashCompletion(),
        note: "Add this to your shell profile if needed: source ~/.gitig-completion.bash",
      };
    case "zsh":
      return {
        path: join(homedir(), ".zsh", "completions", "_gitig"),
        content: renderZshCompletion(),
        note: "Add this to your ~/.zshrc if needed: fpath=(~/.zsh/completions $fpath) && autoload -Uz compinit && compinit",
      };
    case "fish":
      return {
        path: join(homedir(), ".config", "fish", "completions", "gitig.fish"),
        content: renderFishCompletion(),
        note: "Fish should load this automatically in new shells.",
      };
    default:
      throw new Error("install-completion requires one of: bash, zsh, fish");
  }
}

async function cmdInstallCompletion(shellName: string): Promise<void> {
  const target = getCompletionInstallTarget(shellName);
  await ensureDir(dirname(target.path));
  await Bun.write(target.path, target.content);
  console.log(`Installed ${shellName} completion to ${target.path}`);
  console.log(target.note);
}

function printDoctorChecks(title: string, checks: DoctorCheck[]): void {
  console.log(`\n${title}`);
  for (const check of checks) {
    const icon = check.ok ? "OK " : "NO ";
    console.log(`  ${icon} ${check.name}: ${check.detail}`);
  }
}

async function canReadWriteDir(path: string): Promise<boolean> {
  try {
    await ensureDir(path);
    const probe = join(path, ".gitig-write-test");
    await Bun.write(probe, "ok");
    await Bun.file(probe).delete();
    return true;
  } catch {
    return false;
  }
}

async function safeLoadCatalog(source: SourceName, noCache: boolean): Promise<{ ok: boolean; detail: string; count: number }> {
  try {
    const catalog = await getCatalog(source, noCache);
    return {
      ok: true,
      detail: `${catalog.length} templates available`,
      count: catalog.length,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      detail: message,
      count: 0,
    };
  }
}

function getPlatformSummary(): string {
  const p = platform();
  if (p === "darwin") {
    return "darwin (macOS)";
  }
  if (p === "win32") {
    return "win32 (Windows)";
  }
  return `${p} (Unix-like)`;
}

async function cmdDoctor(noCache: boolean): Promise<void> {
  const envChecks: DoctorCheck[] = [];
  const providerChecks: DoctorCheck[] = [];
  const detectChecks: DoctorCheck[] = [];
  const completionChecks: DoctorCheck[] = [];

  const cacheOk = await canReadWriteDir(CACHE_DIR);
  envChecks.push({
    name: "cache directory",
    ok: cacheOk,
    detail: `${CACHE_DIR}${cacheOk ? "" : " is not readable/writable"}`,
  });

  envChecks.push({
    name: "platform",
    ok: true,
    detail: getPlatformSummary(),
  });

  providerChecks.push(
    {
      name: "github all",
      ...(await safeLoadCatalog("github", noCache)),
    },
    {
      name: "github global",
      ...(await safeLoadCatalog("github-global", noCache)),
    },
    {
      name: "github community",
      ...(await safeLoadCatalog("github-community", noCache)),
    },
    {
      name: "gitignore.io",
      ...(await safeLoadCatalog("gitignoreio", noCache)),
    },
  );

  try {
    const ghDetected = await detectTemplates("github", ["os", "editor"]);
    detectChecks.push({
      name: "detect gh",
      ok: true,
      detail: ghDetected.length > 0 ? ghDetected.join(", ") : "no templates detected",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    detectChecks.push({
      name: "detect gh",
      ok: false,
      detail: message,
    });
  }

  try {
    const ghgDetected = await detectTemplates("github-global", ["os", "editor"]);
    detectChecks.push({
      name: "detect ghg",
      ok: true,
      detail: ghgDetected.length > 0 ? ghgDetected.join(", ") : "no templates detected",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    detectChecks.push({
      name: "detect ghg",
      ok: false,
      detail: message,
    });
  }

  try {
    const ttDetected = await detectTemplates("gitignoreio", ["os", "editor"]);
    detectChecks.push({
      name: "detect tt",
      ok: true,
      detail: ttDetected.length > 0 ? ttDetected.join(", ") : "no templates detected",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    detectChecks.push({
      name: "detect tt",
      ok: false,
      detail: message,
    });
  }

  for (const shellName of ["bash", "zsh", "fish"] as const) {
    try {
      const target = getCompletionInstallTarget(shellName);
      completionChecks.push({
        name: `${shellName} completion target`,
        ok: true,
        detail: target.path,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      completionChecks.push({
        name: `${shellName} completion target`,
        ok: false,
        detail: message,
      });
    }
  }

  console.log("gitig doctor");
  printDoctorChecks("Environment", envChecks);
  printDoctorChecks("Providers", providerChecks);
  printDoctorChecks("Detection", detectChecks);
  printDoctorChecks("Completions", completionChecks);

  const allChecks = [...envChecks, ...providerChecks, ...detectChecks, ...completionChecks];
  const failed = allChecks.filter((check) => !check.ok).length;

  console.log(`\nSummary: ${allChecks.length - failed}/${allChecks.length} checks passed`);

  if (failed > 0) {
    process.exit(1);
  }
}

function padRight(value: string, width: number): string {
  if (value.length >= width) {
    return value;
  }
  return value + " ".repeat(width - value.length);
}

function printStatsTable(rows: StatsRow[]): void {
  const labelWidth = rows.reduce((max, row) => Math.max(max, row.label.length), 5);
  const countWidth = rows.reduce((max, row) => Math.max(max, String(row.count).length), 5);

  console.log(`${padRight("Label", labelWidth)}  ${padRight("Count", countWidth)}`);
  console.log(`${"-".repeat(labelWidth)}  ${"-".repeat(countWidth)}`);

  for (const row of rows) {
    console.log(`${padRight(row.label, labelWidth)}  ${padRight(String(row.count), countWidth)}`);
  }
}

async function cmdStats(source: SourceName, noCache: boolean): Promise<void> {
  if (source === "all") {
    const github = await getGitHubCatalog(noCache);
    const gitignoreio = await getGitignoreIoCatalog(noCache);

    const rows: StatsRow[] = [
      { label: "github total", count: github.length },
      {
        label: "github root",
        count: github.filter((entry) => entry.githubScope === "root").length,
      },
      {
        label: "github global",
        count: github.filter((entry) => entry.githubScope === "global").length,
      },
      {
        label: "github community",
        count: github.filter((entry) => entry.githubScope === "community").length,
      },
      { label: "gitignore.io total", count: gitignoreio.length },
      { label: "all combined", count: github.length + gitignoreio.length },
    ];

    printStatsTable(rows);
    return;
  }

  const catalog = await getCatalog(source, noCache);

  let label = source;
  if (source === "github") {
    label = "github";
  } else if (source === "github-global") {
    label = "github global";
  } else if (source === "github-community") {
    label = "github community";
  } else if (source === "gitignoreio") {
    label = "gitignore.io";
  }

  printStatsTable([{ label, count: catalog.length }]);
}

async function main(): Promise<void> {
  try {
    const { command, rest, output, force, source, noCache, noComments, detectIncludes } = parseArgs(Bun.argv.slice(2));

    switch (command) {
      case "list":
        await cmdList(source, noCache);
        return;
      case "search":
        await cmdSearch(rest.join(" "), source, noCache);
        return;
      case "view":
        await cmdView(rest.join(" "), source, noCache, noComments);
        return;
      case "init":
      case "I":
      case "i":
        await cmdInit(rest, source, output, force, noCache, noComments);
        return;
      case "detect":
        await cmdDetect(source, output, force, noCache, detectIncludes, noComments);
        return;
      case "compact":
        await cmdCompact(rest[0], output, force);
        return;
      case "doctor":
        await cmdDoctor(noCache);
        return;
      case "stats":
        await cmdStats(source, noCache);
        return;
      case "completion":
        cmdCompletion(rest[0] ?? "");
        return;
      case "install-completion":
        await cmdInstallCompletion(rest[0] ?? "");
        return;
      case "help":
      case "--help":
      case "-h":
      case undefined:
        printHelp();
        return;
      default:
        console.error(`Unknown command: ${command}`);
        console.error(`Available commands: ${COMMANDS.join(", ")}`);
        printHelp();
        process.exit(1);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Error: ${message}`);
    process.exit(1);
  }
}

await main();
