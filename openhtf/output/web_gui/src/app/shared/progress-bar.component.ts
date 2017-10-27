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
