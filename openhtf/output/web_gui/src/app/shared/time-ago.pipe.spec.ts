/**
 * Tests for time-ago.pipe.ts.
 */

import { TimeAgoPipe } from './time-ago.pipe';

describe('time ago pipe', () => {
  let pipe: TimeAgoPipe;

  beforeEach(() => {
    pipe = new TimeAgoPipe();
  });

  it('should process a timestamp given in milliseconds', () => {
    const laterTime = new Date().getTime() - 5.5 * 60 * 1000;
    expect(pipe.transform(laterTime)).toEqual('5 minutes ago');
  });
});
