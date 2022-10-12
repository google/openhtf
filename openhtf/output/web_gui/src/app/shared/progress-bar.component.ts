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
 * A progress bar.
 */

import { Component, Input } from '@angular/core';

@Component({
  selector: 'htf-progress-bar',
  templateUrl: './progress-bar.component.html',
  styleUrls: ['./progress-bar.component.scss'],
})
export class ProgressBarComponent {
  @Input() value: number;

  private isReset = false;

  get barStyle() {
    if (this.isReset) {
      this.isReset = false;
      return {
        'width': '0',
        'transition': 'none',
      };
    }
    const limitedValue = Math.max(0, Math.min(1, this.value));
    const percent = limitedValue * 100;
    return {
      'width': `${percent}%`,
    };
  }

  get isComplete() {
    return this.value >= 1;
  }

  // Can be triggered by a parent component to animate the progress from zero.
  reset() {
    this.isReset = true;
  }
}
