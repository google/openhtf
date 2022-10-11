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
