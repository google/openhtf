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


declare var $;  // Global provided by the jquery package.

import {Component, Input, OnDestroy, OnInit} from 'angular2/core';
import {RouterLink} from 'angular2/router';
import {RouteParams} from 'angular2/router';


import {HistoryService} from './history.service';
import {Countdown, StatusToColor} from './utils';
import 'file?name=/styles/history.css!./history.css';


/** Dashboard component. **/
@Component({
  selector: 'history',
  template: `
    <div id="history">
      <div class = "big-message">
        {{station_id}}
      </div>
      <div *ngIf="historyService.getTests().length == 0"
            class="big-message">
          No tests to show.
      </div>
      <div *ngIf="historyService.getTests().length > 0">
        <tbody>
          <tr>
              <td>DUT</td>
              <td>Start Time</td>
              <td>End Time</td>
              <td>Outcome</td>
              <td>Outcome Details</td>
              <td>Code Info</td>
          </tr>
          <tr ng-repeat="item in historyService.getTests()">
              <td>{{item.dut}}</td>
              <td>{{item.start_time_millis}}</td>
              <td>{{item.end_time_millis}}</td>
              <td>{{item.outcome}}</td>
              <td>{{item.outcome_details}}</td>
              <td>{{item.code_info}}</td>
          </tr>
        </tbody>
      </div>
    </div>
  `,
  styleUrls: ['styles/history.css'],
  providers: [HistoryService],
})
export class History implements OnInit {

  station_id: string;
  tests: {};

  constructor(private routeParams: RouteParams,
              private historyService: HistoryService) {
    this.station_id = this.routeParams.get('station_id');
    this.historyService.setStationId(this.station_id);
    this.tests = {};
  }

  public ngOnInit(): any{
    this.tests = this.historyService.getTests();
   }
}