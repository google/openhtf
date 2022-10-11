/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
