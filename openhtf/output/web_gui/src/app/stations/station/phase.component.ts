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
