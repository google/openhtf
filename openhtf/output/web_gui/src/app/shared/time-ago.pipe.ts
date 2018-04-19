/**
 * Displays how long ago a given time was.
 */

import { Pipe, PipeTransform } from '@angular/core';

// TODO(Kenadia): Find an open-source implementation of the `relative` function.
const relative = {
  format(_value: number) {
    return '—';
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
