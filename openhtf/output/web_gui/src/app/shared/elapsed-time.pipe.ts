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
