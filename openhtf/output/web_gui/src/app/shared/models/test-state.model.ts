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
  waiting = 9,  // Corresponds to WAITING_FOR_TEST_START.
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
