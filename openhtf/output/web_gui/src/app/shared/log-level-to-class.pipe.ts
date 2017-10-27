import { Pipe, PipeTransform } from '@angular/core';

import { logLevels } from './models/log-record.model';

@Pipe({name: 'logLevelToClass'})
export class LogLevelToClassPipe implements PipeTransform {
  transform(level: number): string {
    if (!level) {
      return;
    }
    if (level <= logLevels.debug) {
      return 'ng-log-level-debug';
    }
    if (level <= logLevels.info) {
      return 'ng-log-level-info';
    }
    if (level <= logLevels.warning) {
      return 'ng-log-level-warning';
    }
    if (level <= logLevels.error) {
      return 'ng-log-level-error';
    }
    return 'ng-log-level-critical';
  }
}
