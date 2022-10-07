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
 * Displays the elapsed time since the start of a test or phase.
 */

import { Pipe, PipeTransform } from '@angular/core';
import { Phase } from './models/phase.model';
import { TestState } from './models/test-state.model';
import { TimeService } from './time.service';

@Pipe({
  name: 'elapsedTime',
  pure: false,
})
export class ElapsedTimePipe implements PipeTransform {
  constructor(private time: TimeService) {}

  transform(obj: Phase|TestState, format = '%s'): string {
    return format.replace('%s', this.getElapsedTimeString(obj));
  }

  getElapsedTimeString(obj: Phase|TestState) {
    if (this.time.last === null) {
      return '0s';
    }
    const endTimeMs = obj.endTimeMillis || this.time.last;
    const elapsedSeconds = Math.round((endTimeMs - obj.startTimeMillis) / 1000);
    const elapsedMinutes = Math.floor(elapsedSeconds / 60);
    if (elapsedMinutes === 0) {
      return `${elapsedSeconds}s`;
    }
    const seconds = elapsedSeconds - 60 * elapsedMinutes;
    const elapsedHours = Math.floor(elapsedMinutes / 60);
    if (elapsedHours === 0) {
      return `${elapsedMinutes}m ${seconds}s`;
    }
    const minutes = elapsedMinutes - 60 * elapsedHours;
    return `${elapsedHours}h ${minutes}m ${seconds}s`;
  }
}
