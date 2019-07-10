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
