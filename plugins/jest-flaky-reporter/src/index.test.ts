import { expect, test } from 'vitest';

import { name } from './index.js';

test('package imports', () => {
  expect(name).toBeTruthy();
});
