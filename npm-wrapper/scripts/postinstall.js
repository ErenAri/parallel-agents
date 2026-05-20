#!/usr/bin/env node

/**
 * Post-install script: check Python availability and install the pip package.
 */

const { execSync } = require("child_process");

const PYPI_PACKAGE = "parallel-agents";

function findPython() {
  for (const cmd of ["python3", "python"]) {
    try {
      const version = execSync(`${cmd} --version 2>&1`, {
        encoding: "utf-8",
      }).trim();
      const parts = version.split(" ")[1].split(".");
      if (parseInt(parts[0]) === 3 && parseInt(parts[1]) >= 11) {
        return cmd;
      }
    } catch {
      // continue
    }
  }
  return null;
}

const python = findPython();
if (!python) {
  console.warn(
    `\n⚠️  Python 3.11+ not found. parallel-agents requires Python.\n` +
      `   Install from https://python.org then run:\n` +
      `   ${python || "python3"} -m pip install ${PYPI_PACKAGE}\n`
  );
  process.exit(0); // don't fail npm install
}

try {
  execSync(`${python} -m pip show ${PYPI_PACKAGE}`, { stdio: "pipe" });
  console.log(`✓ ${PYPI_PACKAGE} Python package already installed`);
} catch {
  console.log(`Installing ${PYPI_PACKAGE} Python package...`);
  try {
    execSync(`${python} -m pip install ${PYPI_PACKAGE}`, { stdio: "inherit" });
    console.log(`✓ ${PYPI_PACKAGE} installed successfully`);
  } catch {
    console.warn(
      `\n⚠️  Failed to auto-install ${PYPI_PACKAGE}. Run manually:\n` +
        `   ${python} -m pip install ${PYPI_PACKAGE}\n`
    );
  }
}
