#!/usr/bin/env node
/**
 * Run a command from inside the backend virtualenv, without needing `make` or an
 * activated shell. Resolves the venv's bin/ (POSIX) or Scripts/ (Windows), so
 * `npm run dev-api` behaves the same on macOS, Linux and Windows.
 *
 *   node scripts/run.mjs backend uvicorn app.main:app --reload --port 8000
 *   node scripts/run.mjs backend --env FOO=1 python -m pytest
 *
 * `--env KEY=VALUE` may be repeated and must come before the command. It exists
 * because `FOO=1 cmd` is not valid on Windows, and the npm scripts have to work
 * there too.
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const argv = process.argv.slice(2);
const workdir = argv.shift();

// Pull any leading `--env KEY=VALUE` pairs off the front.
const extraEnv = {};
while (argv[0] === "--env") {
  argv.shift();
  const pair = argv.shift();
  if (!pair || !pair.includes("=")) {
    console.error("--env expects KEY=VALUE");
    process.exit(2);
  }
  const index = pair.indexOf("=");
  extraEnv[pair.slice(0, index)] = pair.slice(index + 1);
}

const [command, ...args] = argv;
if (!workdir || !command) {
  console.error("usage: node scripts/run.mjs <workdir> [--env KEY=VALUE]... <command> [args...]");
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
  env: {
    ...process.env,
    ...extraEnv,
    PATH: `${binDir}${isWindows ? ";" : ":"}${process.env.PATH ?? ""}`,
  },
});

child.on("exit", (code, signal) => process.exit(signal ? 1 : (code ?? 0)));
child.on("error", (err) => {
  console.error(`Failed to run ${executable}: ${err.message}`);
  process.exit(1);
});
