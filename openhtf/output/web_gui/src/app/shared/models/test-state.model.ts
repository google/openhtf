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
 * The state of a test on a station.
 */

import { Attachment } from './attachment.model';
import { LogRecord } from './log-record.model';
import { Phase } from './phase.model';
import { Station } from './station.model';

// Enum values must not overlap between any of the status enums.
// See status-pipes.ts.
export enum TestStatus {
  waiting = 11,  // Corresponds to WAITING_FOR_TEST_START.
  running,
  pass,
  fail,
  error,
  timeout,
  aborted,
}

export class PlugDescriptor { mro: string[]; }

export class TestState {
  attachments: Attachment[];
  dutId: string;
  endTimeMillis: number|null;
  fileName: string|null;  // This is null for tests *not* from the history.
  name: string;
  logs: LogRecord[];
  phases: Phase[];
  plugDescriptors: {[name: string]: PlugDescriptor};
  plugStates: {[name: string]: {}};
  startTimeMillis: number;
  station: Station;
  status: TestStatus;
  // This is the execution UID. It is null for tests retrieved from the history.
  testId: string|null;

  // Using the class as the interface for its own constructor allows us to call
  // the constructor in named-argument style.
  constructor(params: TestState) {
    Object.assign(this, params);
  }
}
