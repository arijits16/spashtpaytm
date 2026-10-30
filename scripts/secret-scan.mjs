#!/usr/bin/env node
/**
 * Secret scanner (build plan section 13.3).
 *
 * Prefers `gitleaks` when it is installed. Otherwise it runs the fallback
 * patterns the plan specifies over the files git actually knows about - which is
 * the point: a secret only matters once it is staged or committed, and scanning
 * the working tree would drown in `node_modules` and `.venv`.
 *
 * Two modes:
 *   (default)   scan tracked files            - used by `make secret-scan` / `make lint`
 *   --staged    scan the staged diff only     - used by .githooks/pre-commit
 *
 * A line may opt out with the marker `spasht-secret-scan:allow`, which exists so
 * documentation can name a pattern without tripping over it. Use it only for
 * text that is genuinely not a secret.
 *
 * Exit code 0 = clean, 1 = findings, 2 = the scanner itself could not run.
 */

import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync, statSync } from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(import.meta.dirname, "..");
const ALLOW_MARKER = "spasht-secret-scan:allow";

/** The patterns from section 13.3, plus the obvious private-key headers. */
const RULES = [
  { name: "generic secret key (sk_…)", re: /sk_[A-Za-z0-9_]{10,}/ },
  { name: "Google API key (AIza…)", re: /AIza[0-9A-Za-z_-]{35}/ },
  { name: "PEM block header", re: /-----BEGIN/ },
  { name: "private key material", re: /PRIVATE KEY/ },
  { name: "populated DEMO_AUTH_KEY", re: /DEMO_AUTH_KEY=.+/ },
  { name: "populated SARVAM_API_KEY", re: /SARVAM_API_KEY=.+/ },
  { name: "Firebase service-account JSON", re: /"type"\s*:\s*"service_account"/ },
];

/**
 * Files exempt from scanning.
 *
 * Only two: this scanner (it contains every pattern by definition) and the
 * build plan (it documents the patterns and the env-var names). Nothing that
 * could carry a real credential is exempt.
 */
const EXEMPT = new Set(["scripts/secret-scan.mjs", "docs/BUILD_PLAN.md"]);

/** Extensions that are never text we can usefully grep. */
const BINARY_EXT = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".pdf",
  ".mp3",
  ".m4a",
  ".wav",
  ".ico",
  ".woff",
  ".woff2",
  ".ttf",
  ".otf",
  ".zip",
  ".car",
]);

const MAX_BYTES = 2 * 1024 * 1024;

function git(args) {
  return execFileSync("git", args, { cwd: REPO_ROOT, encoding: "utf8" });
}

function hasGitleaks() {
  const probe = spawnSync("gitleaks", ["version"], { stdio: "ignore" });
  return probe.status === 0;
}

/** Run gitleaks, returning true when it reports no findings. */
function runGitleaks(staged) {
  const args = staged
    ? ["protect", "--staged", "--redact", "--no-banner"]
    : ["detect", "--redact", "--no-banner"];
  console.log(`==> gitleaks ${args[0]}`);
  const result = spawnSync("gitleaks", args, { cwd: REPO_ROOT, stdio: "inherit" });
  return result.status === 0;
}

/** Paths to scan: staged additions, or everything git tracks. */
function filesToScan(staged) {
  const raw = staged
    ? git(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    : git(["ls-files"]);
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((file) => !EXEMPT.has(file))
    .filter((file) => !BINARY_EXT.has(path.extname(file).toLowerCase()));
}

function readIfText(file) {
  const abs = path.join(REPO_ROOT, file);
  try {
    if (statSync(abs).size > MAX_BYTES) return null;
    const buffer = readFileSync(abs);
    // A NUL byte means binary, whatever the extension claimed.
    if (buffer.includes(0)) return null;
    return buffer.toString("utf8");
  } catch {
    // Deleted between `git ls-files` and now, or unreadable. Nothing to scan.
    return null;
  }
}

function scan(files) {
  const findings = [];
  for (const file of files) {
    const text = readIfText(file);
    if (text === null) continue;

    text.split("\n").forEach((line, index) => {
      if (line.includes(ALLOW_MARKER)) return;
      for (const rule of RULES) {
        if (rule.re.test(line)) {
          findings.push({ file, line: index + 1, rule: rule.name });
        }
      }
    });
  }
  return findings;
}

function main() {
  const staged = process.argv.includes("--staged");

  if (hasGitleaks()) {
    process.exit(runGitleaks(staged) ? 0 : 1);
  }

  const files = filesToScan(staged);
  console.log(
    `==> secret scan (fallback patterns, gitleaks not installed): ${files.length} ${
      staged ? "staged" : "tracked"
    } file(s)`,
  );

  const findings = scan(files);
  if (findings.length === 0) {
    console.log("    clean");
    process.exit(0);
  }

  // Report the location only. Printing the matched text would copy the secret
  // into the terminal and the CI log, which is the thing we are preventing.
  console.error(`\n✗ ${findings.length} possible secret(s) found:\n`);
  for (const { file, line, rule } of findings) {
    console.error(`  ${file}:${line}  ${rule}`);
  }
  console.error(
    "\nRemove the secret, or move it to a gitignored .env file. If the line is " +
      `genuinely not a secret, append the marker "${ALLOW_MARKER}" to it.\n`,
  );
  process.exit(1);
}

try {
  main();
} catch (error) {
  console.error("secret scan could not run:", error instanceof Error ? error.message : error);
  process.exit(2);
}
