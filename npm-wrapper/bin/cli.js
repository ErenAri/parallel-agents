#!/usr/bin/env node

/**
 * parallel-agents npm wrapper
 *
 * Thin wrapper that delegates to the Python `parallel-agents` CLI.
 * Ensures Python + pip package are available, then forwards all arguments.
 */

const { spawn, execSync } = require("child_process");
const path = require("path");

const PYPI_PACKAGE = "parallel-agents";
const CLI_COMMAND = "parallel-agents";

function findPython() {
  const candidates = ["python3", "python"];
  for (const cmd of candidates) {
    try {
      const version = execSync(`${cmd} --version 2>&1`, {
        encoding: "utf-8",
      }).trim();
      const major = parseInt(version.split(" ")[1].split(".")[0], 10);
      const minor = parseInt(version.split(" ")[1].split(".")[1], 10);
      if (major === 3 && minor >= 11) {
        return cmd;
      }
    } catch {
      // not found, try next
    }
  }
  return null;
}

function isPipPackageInstalled(python) {
  try {
    execSync(`${python} -m pip show ${PYPI_PACKAGE} 2>&1`, {
      encoding: "utf-8",
      stdio: "pipe",
    });
    return true;
  } catch {
    return false;
  }
}

function installPipPackage(python) {
  console.log(`Installing ${PYPI_PACKAGE} via pip...`);
  try {
    execSync(`${python} -m pip install ${PYPI_PACKAGE}`, {
      stdio: "inherit",
    });
    return true;
  } catch {
    return false;
  }
}

function findCLI(python) {
  // Try direct command first
  try {
    execSync(`${CLI_COMMAND} --help`, { stdio: "pipe" });
    return CLI_COMMAND;
  } catch {
    // Fall back to python -m
    return null;
  }
}

function main() {
  const python = findPython();
  if (!python) {
    console.error(
      "Error: Python 3.11+ is required but not found.\n" +
        "Install Python from https://python.org or via your package manager."
    );
    process.exit(1);
  }

  if (!isPipPackageInstalled(python)) {
    if (!installPipPackage(python)) {
      console.error(
        `Error: Failed to install ${PYPI_PACKAGE}.\n` +
          `Try manually: ${python} -m pip install ${PYPI_PACKAGE}`
      );
      process.exit(1);
    }
  }

  // Forward all args to the Python CLI
  const args = process.argv.slice(2);
  const directCLI = findCLI(python);

  let child;
  if (directCLI) {
    child = spawn(directCLI, args, { stdio: "inherit" });
  } else {
    child = spawn(python, ["-m", "parallel_agents.main", ...args], {
      stdio: "inherit",
    });
  }

  child.on("exit", (code) => {
    process.exit(code || 0);
  });

  child.on("error", (err) => {
    console.error(`Failed to start parallel-agents: ${err.message}`);
    process.exit(1);
  });
}

main();
