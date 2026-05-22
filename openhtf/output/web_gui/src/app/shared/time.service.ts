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
 * Service which provides the current time in milliseconds.
 */

import { Injectable } from '@angular/core';
import { interval, ConnectableObservable } from 'rxjs';
import { map, publish } from 'rxjs/operators';

const UPDATE_INTERVAL_MS = 100;

@Injectable()
export class TimeService {
  readonly observable = interval(UPDATE_INTERVAL_MS).pipe(
    map(() => {
      this.last = Date.now();
      return this.last;
    }),
    publish()
  ) as ConnectableObservable<number>;
  last: number|null = null;

  constructor() {
    this.observable.connect();
  }
}
