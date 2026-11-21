import { test, expect } from '@playwright/test';

test('stable', () => {
  expect(1).toBe(1);
});

test('fails then passes', ({}, testInfo) => {
  expect(testInfo.retry, 'first attempt fails').toBeGreaterThanOrEqual(1);
});

test('fails twice then passes', ({}, testInfo) => {
  expect(testInfo.retry, 'attempt fails').toBeGreaterThanOrEqual(2);
});

test('always fails', () => {
  expect(1, 'always fails').toBe(2);
});

for (const region of ['eu', 'us']) {
  test(`param flaky [${region}]`, ({}, testInfo) => {
    if (region === 'eu') expect(testInfo.retry, 'eu first attempt fails').toBeGreaterThanOrEqual(1);
  });
}

test.describe('Checkout', () => {
  test.describe('saved card', () => {
    test('pays', () => {
      expect(1).toBe(1);
    });
  });
});
