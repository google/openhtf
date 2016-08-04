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

import {LoggingLevelToColor, ObjectToUl} from './utils';
import 'file?name=/styles/station.metadata.css!./station.metadata.css';


/** Metadata component; a listing of test metadata. **/
@Component({
  selector: 'metadata',
  template: `
    <div class="meta-listing">
      <div *ngIf="!metadata"
           class="big-message">
        Test metadata is currently unpopulated.
      </div>
      <div *ngIf="metadata"
           class="{{20 | loggingLevelToColor}}"
           [innerHTML]="metadata | objectToUl">
      </div>
    </div>
  `,
  styleUrls: ['styles/station.metadata.css'],
  pipes: [LoggingLevelToColor, ObjectToUl]
})
export class Metadata {
  @Input() metadata: any;
}
