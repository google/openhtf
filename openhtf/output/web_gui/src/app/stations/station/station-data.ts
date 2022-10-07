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
 * Functions for processing data from the station API.
 */

import { Attachment } from '../../shared/models/attachment.model';
import { LogRecord } from '../../shared/models/log-record.model';
import { Measurement, MeasurementStatus } from '../../shared/models/measurement.model';
import { Phase, PhaseStatus } from '../../shared/models/phase.model';
import { Station } from '../../shared/models/station.model';
import { PlugDescriptor, TestState, TestStatus } from '../../shared/models/test-state.model';

import { sortByProperty } from '../../shared/util';

const testStateStatusCompleted = 'COMPLETED';

const testStateStatusMap = {
  'WAITING_FOR_TEST_START': TestStatus.waiting,
  'RUNNING': TestStatus.running,
};

const testRecordOutcomeMap = {
  'PASS': TestStatus.pass,
  'FAIL': TestStatus.fail,
  'ERROR': TestStatus.error,
  'TIMEOUT': TestStatus.timeout,
  'ABORTED': TestStatus.aborted,
};

const measurementStatusMap = {
  'PASS': MeasurementStatus.pass,
  'FAIL': MeasurementStatus.fail,
  'UNSET': MeasurementStatus.unset,
  'PARTIALLY_SET': MeasurementStatus.unset,
};

const phaseRecordOutcomeMap = {
  'PASS': PhaseStatus.pass,
  'FAIL': PhaseStatus.fail,
  'SKIP': PhaseStatus.skip,
  'ERROR': PhaseStatus.error,
};

export interface RawTestState {
  plugs: RawPlugsInfo;
  running_phase_state: RawPhase|null;
  status: string;
  test_record: RawTestRecord;
}

export interface RawPlugsInfo {
  plug_descriptors: {[name: string]: PlugDescriptor};
  plug_states: {[name: string]: {}};
}

export interface RawTestRecord {
  code_info: {};
  dut_id: string;
  end_time_millis?: number;
  log_records: RawLogRecord[];
  metadata: RawMetadata;
  outcome: string;
  outcome_details: Array<{}>;
  phases: RawPhase[];
  start_time_millis: number;
  station_id: string;
}

export interface RawLogRecord {
  level: number;
  lineno: number;
  logger_name: string;
  message: string;
  source: string;
  timestamp_millis: number;
}

export interface RawMetadata { test_name: string; }

export interface RawPhase {
  attachments: {[name: string]: RawAttachment};
  codeinfo: {};
  descriptor_id: number;
  end_time_millis?: number;
  measurements: {[name: string]: RawMeasurement};
  name: string;
  result?: {};  // Not present on running phase state.
  start_time_millis: number;
  outcome: string;
}

export interface RawAttachment {
  mimetype: string;
  sha1: string;
}

export interface RawMeasurement {
  name: string;
  validators?: {};      // Not present on running phase or phase descriptor.
  measured_value?: {};  // Not present on running phase or phase descriptor.
  outcome: string;
}

export interface RawPhaseDescriptor {
  id: number;
  name: string;
  measurements: RawMeasurement[];
}

export function makeTest(
    rawState: RawTestState, testId: string|null, fileName: string|null,
    station: Station) {
  if ((testId === null && fileName === null) ||
      (testId !== null && fileName !== null)) {
    throw new Error('Exactly one of `testId` and `fileName` must be null.');
  }

  // Process the logs.
  const logRecords = rawState.test_record.log_records.filter(log => {
    return log.logger_name !== 'openhtf.output.web_gui';
  });
  logRecords.reverse();  // Sort the logs from most to least recent.
  const logs = logRecords.map(makeLog);

  // Process the phases.
  const phases = rawState.test_record.phases.map(phase => {
    return makePhase(phase, false);
  });
  if (rawState.running_phase_state !== null) {
    phases.push(makePhase(rawState.running_phase_state, true));
  }

  // TODO(kenadia): Make the guarantee that a test state is immutable. Then
  // we should no longer need to preprocess this here or add the attachments
  // directly to the test state.
  //
  // Flatten the lists of attachments.
  const attachments = phases.reduce((accumulator, phase) => {
    return accumulator.concat(phase.attachments);
  }, []);

  // Process the test status.
  let status;
  if (rawState.status === testStateStatusCompleted) {
    status = testRecordOutcomeMap[rawState.test_record.outcome];
  } else {
    status = testStateStatusMap[rawState.status];
  }

  return new TestState({
    attachments,
    dutId: rawState.test_record.dut_id,
    endTimeMillis: rawState.test_record.end_time_millis || null,
    fileName,
    logs,
    name: rawState.test_record.metadata.test_name,
    phases,
    plugDescriptors: rawState.plugs.plug_descriptors,
    plugStates: rawState.plugs.plug_states,
    startTimeMillis: rawState.test_record.start_time_millis,
    station,
    status,
    testId,
  });
}

function makePhase(phase: RawPhase, running: boolean) {
  // Legacy support: phase.attachments in a test record may be undefined.
  let attachments = [];
  if (phase.attachments) {
    attachments = Object.keys(phase.attachments).map(name => {
      const rawAttachment = phase.attachments[name];
      return new Attachment({
        mimeType: rawAttachment.mimetype,
        name,
        phaseDescriptorId: phase.descriptor_id,
        phaseName: phase.name,
        sha1: rawAttachment.sha1,
      });
    });
  }
  // Sort attachments alphabetically by name.
  sortByProperty(attachments, 'name');

  // TODO(kenadia):
  // Observed a bug where phase.measurements is sometimes null or undefined.
  // Figure out why that happens.
  let measurements: Measurement[];
  if (phase.measurements) {
    measurements = Object.keys(phase.measurements).map(key => {
      const rawMeasuredValue = phase.measurements[key].measured_value;
      let measuredValue = null;
      if (typeof rawMeasuredValue !== 'undefined') {
        measuredValue = `${rawMeasuredValue}`;
      }
      return new Measurement({
        name: phase.measurements[key].name,
        validators: phase.measurements[key].validators || null,
        measuredValue,
        status: measurementStatusMap[phase.measurements[key].outcome],
      });
    });
    // Sort measurements alphabetically by name.
    sortByProperty(measurements, 'name');
  } else {
    measurements = [];
  }

  let status: PhaseStatus;
  if (running) {
    status = PhaseStatus.running;
  } else {
    status = phaseRecordOutcomeMap[phase.outcome];
  }
  return new Phase({
    attachments,
    descriptorId: phase.descriptor_id,
    endTimeMillis: phase.end_time_millis || null,
    name: phase.name,
    startTimeMillis: phase.start_time_millis,
    status,
    measurements,
  });
}

export function makePhaseFromDescriptor(descriptor: RawPhaseDescriptor) {
  return new Phase({
    attachments: [],
    descriptorId: descriptor.id,
    endTimeMillis: null,
    name: descriptor.name,
    startTimeMillis: null,
    status: PhaseStatus.waiting,
    measurements: descriptor.measurements.map(measurement => {
      return new Measurement({
        name: measurement.name,
        validators: null,
        measuredValue: null,
        status: measurementStatusMap[measurement.outcome],
      });
    }),
  });
}

function makeLog(log: RawLogRecord) {
  return new LogRecord({
    level: log.level,
    lineNumber: log.lineno,
    loggerName: log.logger_name,
    message: log.message,
    source: log.source,
    timestampMillis: log.timestamp_millis,
  });
}
