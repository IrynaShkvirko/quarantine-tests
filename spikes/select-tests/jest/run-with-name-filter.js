'use strict';
/* Strategy "name": run Jest with -t built from the file, without going through a shell. */
const { run } = require('jest');
const { nameRegex } = require('./quarantine-select');

const mode = process.env.FQ_QUARANTINE_MODE;
const argv = process.argv.slice(2);
const rx = nameRegex(process.env.FQ_QUARANTINE_FILE, mode);
if (rx) argv.push('--testNamePattern', rx);
run(argv);
