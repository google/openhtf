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

import { animate, state, style, transition } from '@angular/animations';

export const washIn = [
  state('in', style({
          'background': 'rgba(0, 119, 255, 0.0)',
        })),
  transition(
      'void => in',
      [
        style({
          'background': 'rgba(0, 119, 255, 0.1)',
        }),
        animate(1000),
      ]),
];

export function washAndExpandIn(maxHeight) {
  return [
    state('in', style({
            'background': 'rgba(0, 119, 255, 0.0)',
            'max-height': `${maxHeight}px`,
          })),
    transition(
        'void => in',
        [
          style({
            'background': 'rgba(0, 119, 255, 0.2)',
            'max-height': '0',
          }),
          animate(500),
        ]),
  ];
}
