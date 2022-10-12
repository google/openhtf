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

import { MeasurementStatus } from './measurement.model';
import { PhaseStatus } from './phase.model';
import { StationStatus } from './station.model';
import { TestStatus } from './test-state.model';

const enumTypes = [MeasurementStatus, PhaseStatus, StationStatus, TestStatus];

function getEnumNames(enumType) {
  return Object.keys(enumType)
      .map(key => enumType[key])
      .filter(value => typeof value === 'string');
}

function getEnumValues(enumType) {
  return Object.keys(enumType)
      .map(key => enumType[key])
      .filter(value => typeof value === 'number');
}

describe('status enums', () => {
  it('should not overlap with one another', () => {
    const nameCount = enumTypes.reduce((nameCountAcc, enumType) => {
      return nameCountAcc + getEnumNames(enumType).length;
    }, 0);
    const valueCount = new Set(enumTypes.reduce((valuesListAcc, enumType) => {
                         return valuesListAcc.concat(getEnumValues(enumType));
                       }, [])).size;
    expect(nameCount).toEqual(valueCount);
  });
});
