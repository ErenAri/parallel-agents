#!/usr/bin/env node

/**
 * Post-install script: check Python availability and install the pip package.
 */

const { execSync } = require("child_process");

const PYPI_PACKAGE = "parallel-agents";
const MIN_PY_MAJOR = 3;
const MIN_PY_MINOR = 11;

function parseVersion(output) {
  const match = output.match(/Python\s+(\d+)\.(\d+)/i);
  if (!match) return null;
  return { major: Number(match[1]), minor: Number(match[2]) };
}

function isSupportedVersion(version) {
  if (!version) return false;
  if (version.major > MIN_PY_MAJOR) return true;
  return version.major === MIN_PY_MAJOR && version.minor >= MIN_PY_MINOR;
}

function findPython() {
  for (const cmd of ["python3", "python"]) {
    try {
      const output = execSync(`${cmd} --version 2>&1`, {
        encoding: "utf-8",
      }).trim();
      const version = parseVersion(output);
      if (isSupportedVersion(version)) {
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
    `\nWarning: Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ not found. parallel-agents requires Python.\n` +
      "Install from https://python.org then run:\n" +
      `  python3 -m pip install ${PYPI_PACKAGE}\n`
  );
  process.exit(0); // do not fail npm install
}

try {
  execSync(`${python} -m pip show ${PYPI_PACKAGE}`, { stdio: "pipe" });
  console.log(`OK ${PYPI_PACKAGE} Python package already installed`);
} catch {
  console.log(`Installing ${PYPI_PACKAGE} Python package...`);
  try {
    execSync(`${python} -m pip install ${PYPI_PACKAGE}`, { stdio: "inherit" });
    console.log(`OK ${PYPI_PACKAGE} installed successfully`);
  } catch {
    console.warn(
      `\nWarning: Failed to auto-install ${PYPI_PACKAGE}. Run manually:\n` +
        `  ${python} -m pip install ${PYPI_PACKAGE}\n`
    );
  }
}

