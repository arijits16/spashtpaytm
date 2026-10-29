#!/usr/bin/env node
/**
 * Cross-platform `make setup`: creates the backend virtualenv, installs both
 * dependency sets, and copies the .env.example files into place.
 *
 * Mirrors the Makefile `setup` target so Windows teammates get the same result.
 */
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";

// Pinned to 3.12: the system default (3.15) lacks reliable psycopg/pydantic wheels.
const PYTHON = process.env.PYTHON ?? (isWindows ? "py -3.12" : "python3.12");
const VENV = join(ROOT, "backend", ".venv");
const VENV_BIN = join(VENV, isWindows ? "Scripts" : "bin");
const VENV_PY = join(VENV_BIN, isWindows ? "python.exe" : "python");

/** Run a command, inheriting stdio, and abort the script on failure. */
function run(cmd, args, cwd = ROOT) {
  console.log(`\n$ ${cmd} ${args.join(" ")}`);
  const result = spawnSync(cmd, args, { cwd, stdio: "inherit", shell: isWindows });
  if (result.status !== 0) {
    console.error(`\nFailed: ${cmd} ${args.join(" ")}`);
    process.exit(result.status ?? 1);
  }
}

function has(cmd) {
  const probe = spawnSync(isWindows ? "where" : "which", [cmd], { stdio: "ignore" });
  return probe.status === 0;
}

console.log("==> backend environment");
if (has("uv")) {
  console.log("    uv found");
  run("uv", ["venv", "--python", PYTHON, VENV]);
  run("uv", ["pip", "install", "--python", VENV_PY, "-e", "backend[dev]"]);
} else {
  console.log(`    uv not found, using ${PYTHON} -m venv`);
  if (!existsSync(VENV)) {
    const [bin, ...rest] = PYTHON.split(" ");
    run(bin, [...rest, "-m", "venv", VENV]);
  }
  run(VENV_PY, ["-m", "pip", "install", "--quiet", "--upgrade", "pip"]);
  run(VENV_PY, ["-m", "pip", "install", "-e", "backend[dev]"]);
}

console.log("\n==> frontend dependencies");
run("npm", ["install"], join(ROOT, "frontend"));

console.log("\n==> .env files (never committed)");
for (const dir of ["backend", "frontend"]) {
  const target = join(ROOT, dir, ".env");
  const example = join(ROOT, dir, ".env.example");
  if (existsSync(target)) {
    console.log(`    ${dir}/.env already exists, left alone`);
  } else {
    copyFileSync(example, target);
    console.log(`    ${dir}/.env created from .env.example`);
  }
}

console.log("\n==> done. Next: npm run db-up && npm run migrate && npm run dev");
