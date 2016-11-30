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

import {Component,
        OnDestroy,
        OnInit,
        SimpleChange} from 'angular2/core';
import {RouteParams} from 'angular2/router';

import {Logs} from './station.logs';
import {StationHeader} from './station.header';
import {Metadata} from './station.metadata';
import {PhaseListing} from './station.phases';
import {Prompt} from './station.prompt';
import {StationService} from './station.service';
import {TestHeader} from './station.testheader';
import {Countdown, ObjectToArray} from './utils';
import 'file?name=/styles/station.css!./station.css';
import 'file?name=/templates/station.html!./station.html';


/** Station view component. **/
@Component({
  selector: 'station',
  templateUrl: 'templates/station.html',
  styleUrls: ['styles/station.css'],
  pipes: [ObjectToArray],
  directives: [StationHeader, Prompt, TestHeader, PhaseListing, Logs, Metadata],
  providers: [StationService]
})
export class Station implements OnDestroy, OnInit {
  private stationInfo: any;
  private currentMillis: number;
  private currentMillisJob: number;
  private tests: any[];
  private testUIDs: string[];

  /**
   * Create a Station view component.
   */
  constructor(private routeParams: RouteParams,
              private stationService: StationService) {
    this.currentMillis = setInterval(() => {
      this.currentMillis = Date.now();
    }, 250);
  }

  /**
   * Set up the view component on initialization.
   */
  public ngOnInit(): any{
    $('station-header ul.tabs').tabs();
    this.stationService.setHostPort(this.routeParams.get('host'),
                                    this.routeParams.get('port'));
    this.stationService.subscribe();
    this.stationInfo = this.stationService.getStationInfo();
    this.tests = this.stationService.getTests();
    this.testUIDs = this.stationService.getTestUIDs();
  }

  /**
   * Tear down the view component when navigating away.
   */
  public ngOnDestroy() {
    this.stationService.unsubscribe();
    clearInterval(this.currentMillisJob);
  }
}
