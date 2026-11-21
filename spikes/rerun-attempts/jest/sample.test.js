jest.retryTimes(2, { logErrorsBeforeRetry: true });

// attempt counter per test: afterEach-free, deterministic
const attempts = {};
const attempt = (name) => (attempts[name] = (attempts[name] || 0) + 1);

test('stable', () => {
  expect(1).toBe(1);
});

test('fails then passes', () => {
  expect(attempt('a')).toBeGreaterThanOrEqual(2);
});

test('fails twice then passes', () => {
  expect(attempt('b')).toBeGreaterThanOrEqual(3);
});

test('always fails', () => {
  expect(1).toBe(2);
});

test.each(['eu', 'us'])('param flaky [%s]', (region) => {
  const n = attempt(`p-${region}`);
  if (region === 'eu') expect(n).toBeGreaterThanOrEqual(2);
});

describe('cart total', () => {
  describe('discount', () => {
    test('applies discount', () => {
      expect(1).toBe(1);
    });
  });
});
