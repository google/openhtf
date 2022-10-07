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
 * A phase of a test.
 *
 * May combine both PhaseDescriptor and PhaseState information from the backend.
 */

import { Attachment } from './attachment.model';
import { Measurement } from './measurement.model';

// Enum values must not overlap between any of the status enums.
// See status-pipes.ts.
export enum PhaseStatus {
  waiting = 3,
  running,
  pass,
  fail,
  skip,
  error,
}

export class Phase {
  attachments: Attachment[];
  descriptorId: number;
  endTimeMillis: number|null;
  name: string;
  measurements: Measurement[];
  status: PhaseStatus;
  startTimeMillis: number|null;  // Should only be null if phase is waiting.

  // Using the class as the interface for its own constructor allows us to call
  // the constructor in named-argument style.
  constructor(params: Phase) {
    Object.assign(this, params);
  }
}
