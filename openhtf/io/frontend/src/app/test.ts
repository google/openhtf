// Copyright 2016 Google Inc.All Rights Reserved.

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


/** Represents an active or past test run. **/
export class Test {
  dutID: string;
  startTime: number;
  endTime: number;
  duration: number;
  outcome: string;
  phases: Phase[];
  logEntries: LogEntry[];

  /**
   * Create a Test.
   * @param record - A serialized OpenHTF TestRecord.
   */
  constructor() {
    this.duration = 0;
    this.logEntries = [];
    this.phases = [];
  }

  /**
   * Update state based on a test record.
   * @param test - A serialized OpenHTF TestState.
   * @param phaseList - An option list of phases to override the record.
   */
  update(record: any) {
    // Test state is tricky to track and update particularly because we want
    // log entries and other data displayed in the gui to be selectable. If
    // new components are being created on every update, we will lost active
    // selections even when the gui appears to remain static. Instead, we need
    // to keep the gui _actually_ static when no changes are happening, which
    // means the inputs to view componts need to stay pointing at the same
    // objects in memory. If someone has a better way to do this, please let
    // me know!
    //
    // --jethier
    
    if (!record) {
      // TODO(jethier): Find a more graceful way to handle null records.
      return;
    }

    this.dutID = record.dut_id;

    this.outcome = record.outcome;
    
    this.startTime = +record.start_time_millis;
    this.endTime = +record.end_time_millis;

    let start = this.startTime || Date.now();
    let end = this.endTime || Date.now();
    this.duration = end - start;

    for (var i = this.logEntries.length; i < record.log_records.length; i++) {
      this.logEntries.push(new LogEntry(record.log_records[i]));
    }

    for (var i = 0; i < record.phases.length; i++) {
      this.updatePhase(i, record.phases[i]);
    }
  }

  updatePhase(idx: number, updateObj: any) {
    if (idx > this.phases.length) {
      throw "Unable to update phases that are unknown.";
    }
    if (idx == this.phases.length) {
      this.phases.push(new Phase(updateObj.name));
    }
    this.phases[idx].update(updateObj);
  }
}


/** A test phase. **/
export class Phase {
  private docstring: string;
  private status: string;
  private startTime: number;
  private endTime: number;
  private measurements: Measurement[];
  private attachments: Attachment[];

  /**
   * Create a new Phase.
   * @param {string} name - The name of the phase.
   */
   constructor(private name: string) {
     this.measurements = [];
     this.attachments = [];
     this.status = 'PENDING';
   }

  /**
   * Update a Phase based on a PhaseRecord.
   * @param record - A serialized OpenHTF PhaseRecord.
   */
  update(record: any) {
    if (record.name != this.name) {
      throw "Phase record doesn't match the phase being updated.";
    }

    this.docstring = record.codeinfo.docstring;

    this.startTime = +record.start_time_millis || Date.now();
    this.endTime = +record.end_time_millis || Date.now();
    
    let reckonedStatus = 'PASS';
    this.measurements = [];
    for (let name in record.measurements) {
      let value_record = null;
      if (record.measured_values && record.measured_values.hasOwnProperty(name)) {
        value_record = record.measured_values[name];
      }
      this.measurements.push(
          new Measurement(record.measurements[name], value_record));
      if (record.measurements[name].outcome == 'FAIL') {
        reckonedStatus = 'FAIL';
      }
      if (record.measurements[name].outcome == 'UNSET') {
        reckonedStatus = 'RUNNING';
      }
      this.status = reckonedStatus;
    }

    // TODO(jethier): Do something with attachments.
    this.attachments = [];
  }
}


/** A single measurement. **/
export class Measurement {
  name: string;
  outcome: string;
  validator: string;
  value: string;

  /**
   * Create a Measurement from records.
   * @param record - A serized OpenHTF Measurement.
   * @param value - A serialized OpenHTF MeasuredValue.
   */
  constructor(record, value_record) {
    // TODO(jethier): Account for multi-dimensional measurements. And don't
    //                forget the <phase> template will need to be updated.
    this.name = record.name;
    this.outcome = record.outcome || 'UNSET';
    this.value = value_record || '';
    // TODO(jethier): There must be a better way to do this in js/Typescript.
    if (record.validators && record.validators.length > 0) {
      this.validator = record.validators[0];
    }
  }
}


export class Attachment { }


/** A single log entry. **/
export class LogEntry {
  level: number;
  message: string;
  timestampMillis: number;

   /**
   * Create a LogEntry from a log record.
   * @param logRecord - A serialized OpenHTF LogRecord.
   */
   constructor(logRecord: any) {
     this.level = +logRecord.level;
     this.message = logRecord.message;
     this.timestampMillis = +logRecord.timestamp_millis;
   }
}
