/**
 * Displays how long ago a given time was.
 */

import { Pipe, PipeTransform } from '@angular/core';

// DO NOT MERGE
// We need to find an open-source implementation of the `relative` function.
const relative = {
  format(_value: number) {
    return 'TODO';
  }
};

@Pipe({
  name: 'timeAgo',
  pure: false,
})
export class TimeAgoPipe implements PipeTransform {
  transform(value: number): string {
    return relative.format(value);
  }
}
