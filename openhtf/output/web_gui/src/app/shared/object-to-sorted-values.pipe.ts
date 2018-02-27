/**
 * Pipe which returns the values of an object, sorted by key.
 *
 * This helps us to iterate over objects in templates using ngFor.
 */

import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'objectToSortedValues',
  // Marking this pipe impure means it will be called on every change detection
  // cycle. Be careful about using this with anything other than small objects.
  pure: false,
})
export class ObjectToSortedValuesPipe implements PipeTransform {
  transform(object: {}, sortBy: string|null = null) {
    const asArray = [];
    const keys = Object.keys(object);
    // Sort by key if sortBy is not defined.
    if (sortBy === null) {
      keys.sort();
    }
    for (const key of keys) {
      asArray.push(object[key]);
    }
    // Sort the values by sortBy if it is defined.
    if (sortBy !== null) {
      asArray.sort((a, b) => {
        if (a[sortBy] < b[sortBy]) {
          return -1;
        } else if (a[sortBy] > b[sortBy]) {
          return 1;
        }
        return 0;
      });
    }
    return asArray;
  }
}
