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


import {Component, Input}     from 'angular2/core';

import {MillisUTCToLocalStr, LoggingLevelToColor} from './utils';

import 'file?name=/styles/station.logs.css!./station.logs.css';


/** Logs view component; a listing of log entries. **/
@Component({
  selector: 'logs',
  template: `
    <div class="log-listing">
      <div *ngIf="logEntries.length == 0" class="center-align grey-text">
        <h5>Log is currently empty.</h5>
      </div>
      <div *ngFor="let entry of logEntries"
            class="log-entry {{entry.level | loggingLevelToColor}}">
        <span class='timestamp'>
          {{entry.timestampMillis | millisUTCToLocalStr}}
        </span>
        {{entry.message}}
      </div>
    </div>
  `,
  styleUrls: ['styles/station.logs.css'],
  pipes: [MillisUTCToLocalStr, LoggingLevelToColor]
})
export class Logs {
  @Input() logEntries: any[];
}
