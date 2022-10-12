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
 * Widget displaying a test run's logs.
 */

import { Component, Input } from '@angular/core';

import { logLevels } from '../../shared/models/log-record.model';
import { TestState } from '../../shared/models/test-state.model';

@Component({
  selector: 'htf-logs',
  templateUrl: './logs.component.html',
  styleUrls: ['./logs.component.scss'],
})
export class LogsComponent {
  @Input() test: TestState;

  expanded = false;

  get collapsedErrorCount() {
    // Count the number of log errors, excluding the most recent log line, which
    // is always visible.
    let count = 0;
    for (const log of this.test.logs) {
      if (log.level > logLevels.warning) {
        count += 1;
      }
    }
    if (this.test.logs[0].level > logLevels.warning) {
      count -= 1;
    }
    return count;
  }

  toggleExpanded() {
    this.expanded = !this.expanded;
  }
}
