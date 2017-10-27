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
