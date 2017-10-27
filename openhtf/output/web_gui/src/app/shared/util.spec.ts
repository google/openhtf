/**
 * Tests for util.ts.
 */

import { devHost } from './util';

describe('util', () => {
  it('devHost should not be set', () => {
    expect(devHost).toEqual('');
  });
});
