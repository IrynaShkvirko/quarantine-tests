module.exports = {
  testRunner: 'jest-circus/runner',
  reporters: [
    ['jest-junit', { outputDirectory: '.', outputName: 'native.xml' }],
    ['<rootDir>/fq-reporter.js', { outputFile: 'fq.xml' }],
  ],
};
