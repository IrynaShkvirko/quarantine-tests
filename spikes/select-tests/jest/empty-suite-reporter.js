'use strict';
/**
 * Jest fails a test file with zero registered tests ("Your test suite must contain at least one
 * test."). In exclude mode that happens to every file whose tests are all quarantined.
 * This reporter, listed BEFORE jest-junit, turns exactly that failure into a no-op: the suite is
 * removed from the failure counters and the result is cleared so no reporter prints it.
 * It touches Jest result internals (aggregatedResults counters), so it needs a version check.
 */
const MESSAGE = 'Your test suite must contain at least one test.';

class EmptySuiteReporter {
  constructor() {
    this.ignored = [];
  }
  onTestFileResult(test, testResult, aggregatedResults) {
    const err = testResult.testExecError;
    if (testResult.testResults.length !== 0 || !err || err.message !== MESSAGE) return;
    this.ignored.push(testResult.testFilePath);
    aggregatedResults.numFailedTestSuites -= 1;
    aggregatedResults.numRuntimeErrorTestSuites -= 1;
    aggregatedResults.numTotalTestSuites -= 1;
    testResult.testExecError = undefined;
    testResult.failureMessage = null;
  }
  onRunComplete() {
    if (this.ignored.length) console.error(`fq: ${this.ignored.length} fully quarantined file(s) skipped`);
  }
  getLastError() {}
}
module.exports = EmptySuiteReporter;
