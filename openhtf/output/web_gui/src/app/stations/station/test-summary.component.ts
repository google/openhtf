/**
 * Widget displaying summary information about a test.
 */

import { Component, Input, OnChanges, SimpleChanges, ViewChild } from '@angular/core';

import { Phase, PhaseStatus } from '../../shared/models/phase.model';
import { TestState, TestStatus } from '../../shared/models/test-state.model';
import { ProgressBarComponent } from '../../shared/progress-bar.component';

@Component({
  selector: 'htf-test-summary',
  templateUrl: './test-summary.component.html',
  styleUrls: ['./test-summary.component.scss'],
})
export class TestSummaryComponent implements OnChanges {
  @Input() test: TestState;
  @ViewChild(ProgressBarComponent) progressBar: ProgressBarComponent;

  ngOnChanges(changes: SimpleChanges) {
    // When we get a new test, animate the progress bar from zero.
    if ('test' in changes && this.progressBar) {
      this.progressBar.reset();
    }
  }

  get completedPhaseCount() {
    if (this.test.status === TestStatus.waiting) {
      return 0;
    } else if (this.test.status === TestStatus.pass) {
      return this.test.phases.length;
    }

    let completedPhases = 0;
    for (const phase of this.test.phases) {
      if (phase.status === PhaseStatus.running ||
          phase.status === PhaseStatus.fail) {
        break;
      }
      completedPhases++;
    }
    return completedPhases;
  }

  get progressValue() {
    return this.completedPhaseCount / this.test.phases.length;
  }

  get runningPhase(): Phase|null {
    if (this.test.status === TestStatus.running) {
      for (const phase of this.test.phases) {
        if (phase.status === PhaseStatus.running) {
          return phase;
        }
      }
    }
    return null;
  }
}
