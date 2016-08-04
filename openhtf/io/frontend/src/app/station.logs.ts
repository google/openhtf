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


import {Component, Input} from 'angular2/core';

import {LoggingLevelToColor} from './utils';
import 'file?name=/styles/station.logs.css!./station.logs.css';


/** Logs view component; a listing of log entries. **/
@Component({
  selector: 'logs',
  template: `
    <div class="log-listing">
      <div *ngIf="!log_records?.length > 0"
           class="big-message">
        Log is currently empty.
      </div>
      <div *ngFor="let entry of log_records"
            class="log-entry {{entry.level | loggingLevelToColor}}">
        <span class='timestamp'>
          {{entry.timestamp_millis | date:'short'}}
        </span>
        {{entry.message}}
      </div>
    </div>
  `,
  styleUrls: ['styles/station.logs.css'],
  pipes: [LoggingLevelToColor]
})
export class Logs {
  @Input() log_records: any[];
}
