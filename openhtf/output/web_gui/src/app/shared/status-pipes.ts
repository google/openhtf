/**
 * Tools for rendering test and phase status information.
 */

import { Pipe, PipeTransform } from '@angular/core';

import { MeasurementStatus } from './models/measurement.model';
import { PhaseStatus } from './models/phase.model';
import { StationStatus } from './models/station.model';
import { TestStatus } from './models/test-state.model';

enum StatusCategory {
  fail,
  online,
  pass,
  pending,
  running,
  unreachable,
  warning,
}

// We use the ng- prefix to indicate CSS classes that are added dynamically.
const categoryToCssClass = {
  [StatusCategory.fail]: 'ng-status-fail',
  [StatusCategory.online]: 'ng-status-online',
  [StatusCategory.pass]: 'ng-status-pass',
  [StatusCategory.pending]: 'ng-status-pending',
  [StatusCategory.running]: 'ng-status-running',
  [StatusCategory.unreachable]: 'ng-status-unreachable',
  [StatusCategory.warning]: 'ng-status-warning',
};

const unknownStatus = Symbol('unknownStatus');

export type AnyStatus =
    MeasurementStatus | PhaseStatus | StationStatus | TestStatus;

const statusToCategory = {
  [MeasurementStatus.unset]: StatusCategory.pending,
  [MeasurementStatus.pass]: StatusCategory.pass,
  [MeasurementStatus.fail]: StatusCategory.fail,
  [PhaseStatus.waiting]: StatusCategory.pending,
  [PhaseStatus.running]: StatusCategory.running,
  [PhaseStatus.pass]: StatusCategory.pass,
  [PhaseStatus.fail]: StatusCategory.fail,
  [StationStatus.online]: StatusCategory.online,
  [StationStatus.unreachable]: StatusCategory.unreachable,
  [TestStatus.waiting]: StatusCategory.pending,
  [TestStatus.running]: StatusCategory.running,
  [TestStatus.pass]: StatusCategory.pass,
  [TestStatus.fail]: StatusCategory.fail,
  [TestStatus.error]: StatusCategory.warning,
  [TestStatus.timeout]: StatusCategory.warning,
  [TestStatus.aborted]: StatusCategory.warning,
  [unknownStatus]: StatusCategory.warning,
};

const statusToText = {
  [MeasurementStatus.unset]: 'Unset',
  [MeasurementStatus.pass]: 'Pass',
  [MeasurementStatus.fail]: 'Fail',
  [PhaseStatus.waiting]: 'Waiting',
  [PhaseStatus.running]: 'Running',
  [PhaseStatus.pass]: 'Pass',
  [PhaseStatus.fail]: 'Fail',
  [StationStatus.online]: 'Online',
  [StationStatus.unreachable]: 'Unreachable',
  [TestStatus.waiting]: 'Waiting',
  [TestStatus.running]: 'Running',
  [TestStatus.pass]: 'Pass',
  [TestStatus.fail]: 'Fail',
  [TestStatus.error]: 'Error',
  [TestStatus.timeout]: 'Timeout',
  [TestStatus.aborted]: 'Aborted',
  [unknownStatus]: 'Unknown',
};

@Pipe({name: 'statusToClass'})
export class StatusToClassPipe implements PipeTransform {
  transform(input: AnyStatus): string {
    if (!(input in statusToCategory)) {
      console.error(`Unknown status "${input}".`);
      return categoryToCssClass[statusToCategory[unknownStatus]];
    }
    return categoryToCssClass[statusToCategory[input]];
  }
}

@Pipe({name: 'statusToText'})
export class StatusToTextPipe implements PipeTransform {
  transform(input: AnyStatus): string {
    if (!(input in statusToCategory)) {
      console.error(`Unknown status "${input}".`);
      return statusToText[unknownStatus];
    }
    return statusToText[input];
  }
}
