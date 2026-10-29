#!/usr/bin/env node
/**
 * Run a command from inside the backend virtualenv, without needing `make` or an
 * activated shell. Resolves the venv's bin/ (POSIX) or Scripts/ (Windows), so
 * `npm run dev-api` behaves the same on macOS, Linux and Windows.
 *
 *   node scripts/run.mjs backend uvicorn app.main:app --reload --port 8000
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const [workdir, command, ...args] = process.argv.slice(2);
if (!workdir || !command) {
  console.error("usage: node scripts/run.mjs <workdir> <command> [args...]");
  process.exit(2);
}

const isWindows = process.platform === "win32";
const binDir = join(ROOT, workdir, ".venv", isWindows ? "Scripts" : "bin");

if (!existsSync(binDir)) {
  console.error(`No virtualenv at ${binDir}.\nRun "npm run setup" (or "make setup") first.`);
  process.exit(1);
}

// Prefer the venv's executable; fall back to PATH for things like `docker`.
const candidates = isWindows
  ? [`${command}.exe`, `${command}.cmd`, `${command}.bat`, command]
  : [command];
const executable = candidates.map((c) => join(binDir, c)).find(existsSync) ?? command;

const child = spawn(executable, args, {
  cwd: join(ROOT, workdir),
  stdio: "inherit",
  // Put the venv first on PATH so sub-processes resolve the same interpreter.
  env: { ...process.env, PATH: `${binDir}${isWindows ? ";" : ":"}${process.env.PATH ?? ""}` },
});

child.on("exit", (code, signal) => process.exit(signal ? 1 : (code ?? 0)));
child.on("error", (err) => {
  console.error(`Failed to run ${executable}: ${err.message}`);
  process.exit(1);
});
