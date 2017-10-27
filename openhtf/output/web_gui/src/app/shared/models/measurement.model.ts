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
