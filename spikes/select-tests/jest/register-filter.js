'use strict';
/* setupFilesAfterEnv: drop filtered tests at registration time. Runs inside each test file's VM. */
const fs = require('node:fs');
const path = require('node:path');
const { loadKeys, SEP } = require('./quarantine-select');

const mode = process.env.FQ_QUARANTINE_MODE;
const keys = new Set(loadKeys(process.env.FQ_QUARANTINE_FILE));
const relFile = path
  .relative(process.cwd(), expect.getState().testPath)
  .split(path.sep)
  .join('/');
const stack = [];

function keep(name) {
  const listed = keys.has(`${relFile}::${[...stack, name].join(SEP)}`);
  return mode === 'only' ? listed : !listed;
}

function wrapDescribe(orig) {
  const w = (name, fn) =>
    orig(name, function (...args) {
      stack.push(String(name));
      try {
        return fn.apply(this, args);
      } finally {
        stack.pop();
      }
    });
  return Object.assign(w, orig, {
    only: orig.only && ((n, f) => wrapDescribe(orig.only)(n, f)),
    skip: orig.skip && ((n, f) => wrapDescribe(orig.skip)(n, f)),
  });
}

function wrapTest(orig) {
  const w = (name, ...rest) => (keep(String(name)) ? orig(name, ...rest) : undefined);
  return Object.assign(w, orig, {
    only: orig.only && ((n, ...r) => (keep(String(n)) ? orig.only(n, ...r) : undefined)),
    skip: orig.skip && ((n, ...r) => (keep(String(n)) ? orig.skip(n, ...r) : undefined)),
  });
}

globalThis.describe = wrapDescribe(globalThis.describe);
globalThis.test = wrapTest(globalThis.test);
globalThis.it = globalThis.test;
