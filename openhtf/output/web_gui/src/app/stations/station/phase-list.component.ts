/**
 * Widget displaying the phases of a test.
 */

import { Component, Input } from '@angular/core';

import { TestState } from '../../shared/models/test-state.model';

@Component({
  selector: 'htf-phase-list',
  templateUrl: './phase-list.component.html',
})
export class PhaseListComponent {
  @Input() test: TestState;

  showMeasurements = false;

  toggleMeasurements() {
    this.showMeasurements = !this.showMeasurements;
  }
}
