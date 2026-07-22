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
 * Displays how long ago a given time was.
 */

import { Pipe, PipeTransform } from '@angular/core';

const relative = {
  format(value: number) {
    const diffMs = new Date().getTime() - value;
    if (diffMs < 0) return 'in the future';
    const diffMins = Math.floor(diffMs / (60 * 1000));
    if (diffMins < 1) return 'just now';
    if (diffMins === 1) return '1 minute ago';
    if (diffMins < 60) return `${diffMins} minutes ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours === 1) return '1 hour ago';
    if (diffHours < 24) return `${diffHours} hours ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays === 1) return '1 day ago';
    return `${diffDays} days ago`;
  }
};

@Pipe({
    name: 'timeAgo',
    pure: false,
    standalone: false
})
export class TimeAgoPipe implements PipeTransform {
  transform(value: number): string {
    return relative.format(value);
  }
}
