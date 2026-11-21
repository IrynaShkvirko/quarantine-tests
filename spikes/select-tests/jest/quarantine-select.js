'use strict';
/**
 * M0-11 prototype: select Jest tests by quarantine key.
 *
 * Strategy "register" (recommended): a setupFilesAfterEnv file wraps describe/test/it and does not
 * register tests that are filtered out, so they never exist for Jest: no "skipped" entries.
 * Strategy "name": `-t` with a regex built from the file (see run-with-name-filter.js).
 *
 * The list always comes from a file: FQ_QUARANTINE_FILE (+ FQ_QUARANTINE_MODE=exclude|only).
 */
const fs = require('node:fs');
const path = require('node:path');
const { parse } = require('yaml');

const PREFIX = 'jest::';
const SEP = ' > ';

function loadKeys(file) {
  const doc = parse(fs.readFileSync(file, 'utf8')) || {};
  return (doc.tests || [])
    .map((t) => t && t.id)
    .filter((id) => typeof id === 'string' && id.startsWith(PREFIX))
    .map((id) => id.slice(PREFIX.length)); // "<file>::<describe > ... > title>"
}

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\\/-]/g, '\\$&');

function jestConfig() {
  const file = process.env.FQ_QUARANTINE_FILE;
  const mode = process.env.FQ_QUARANTINE_MODE || 'off';
  if (!file || mode === 'off' || process.env.FQ_JEST_STRATEGY === 'name') return {};
  const cfg = { setupFilesAfterEnv: [path.join(__dirname, 'register-filter.js')] };
  if (mode === 'only') {
    // Only open the files that contain listed tests (saves the cost of loading the others).
    const files = [...new Set(loadKeys(file).map((k) => k.slice(0, k.indexOf('::'))))];
    cfg.testRegex = files.length ? files.map((f) => `/${escapeRegExp(f)}$`) : ['^(?!)'];
    cfg.testMatch = undefined;
  }
  return cfg;
}

/** Regex for `-t`: matched by Jest against "describe test" joined with single spaces. */
function nameRegex(file, mode) {
  const names = loadKeys(file).map((k) => k.slice(k.indexOf('::') + 2).split(SEP).join(' '));
  if (names.length === 0) return mode === 'only' ? '^(?!)' : '';
  const alts = names.map(escapeRegExp).join('|');
  return mode === 'only' ? `^(?:${alts})$` : `^(?!(?:${alts})$)`;
}

module.exports = { loadKeys, jestConfig, nameRegex, escapeRegExp, PREFIX, SEP };
