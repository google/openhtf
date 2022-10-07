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
