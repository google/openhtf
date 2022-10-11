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
 * A measurement in a phase of a test.
 */

// Enum values must not overlap between any of the status enums.
// See status-pipes.ts.
export enum MeasurementStatus {
  unset,
  pass,
  fail,
}

export class Measurement {
  name: string;
  validators: {}|null;
  measuredValue: string|null;
  status: MeasurementStatus;

  // Using the class as the interface for its own constructor allows us to call
  // the constructor in named-argument style.
  constructor(params: Measurement) {
    Object.assign(this, params);
  }
}
