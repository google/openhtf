/**
 * Widget displaying the phases of a test.
 */

import { Component, Input } from '@angular/core';

import { MeasurementStatus } from '../../shared/models/measurement.model';
import { Phase, PhaseStatus } from '../../shared/models/phase.model';

@Component({
  selector: 'htf-phase',
  templateUrl: './phase.component.html',
  styleUrls: ['./phase.component.scss'],
})
export class PhaseComponent {
  @Input() phase: Phase;
  @Input() expand: boolean;

  MeasurementStatus = MeasurementStatus;
  PhaseStatus = PhaseStatus;

  get showMeasurements() {
    return this.expand && this.phase.measurements.length > 0;
  }
}
