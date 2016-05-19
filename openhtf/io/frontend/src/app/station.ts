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

import {Component, OnDestroy} from 'angular2/core';
import {RouteParams} from 'angular2/router';

import {Logs} from './station.logs';
import {StationHeader} from './station.header';
import {PhaseListing} from './station.phases';
import {Prompt} from './station.prompt';
import {StationService} from './station.service';
import {TestHeader} from './station.testheader';
import {Test} from './test';
import {Countdown} from './utils';
import 'file?name=/styles/station.css!./station.css';
import 'file?name=/templates/station.html!./station.html';


/** Station view component. **/
@Component({
  selector: 'station',
  templateUrl: 'templates/station.html',
  styleUrls: ['styles/station.css'],
  directives: [StationHeader, Prompt, TestHeader, PhaseListing, Logs],
  providers: [StationService]
})
export class Station implements OnDestroy {
  private framework: any = {};
  private test: Test;
  private stationState: any;
  private lastUpdateTime: number;
  private ip: string;
  private port: string;
  private countdown: Countdown;
  private paused: boolean;
  private pollingJob: number;

  /**
   * Create a Station view component.
   */
  constructor(private routeParams: RouteParams,
              private stationService: StationService) {
    this.paused = false;
    this.stationState = {};
    this.test = new Test();
  }

  /**
   * Pause display updates for the given number of seconds.
   */
  pauseForCountdown(seconds: number) {
    // TODO(jethier): Make the countdown timer look good. Possibly replace the
    //                "current" button temporarily with a radial progress bar.
    // TODO(jethier): Make this timeout configurable.
    this.countdown = new Countdown(seconds);
    this.paused = true;
    this.countdown.onDone = () => { this.paused = false; };
    this.countdown.reset();
    this.countdown.start();
  }

  /**
   * Set up the view component on initialization.
   */
  public ngOnInit(): any{
    $('ul.tabs').tabs();
    this.ip = this.routeParams.get('ip');
    this.port = this.routeParams.get('port');
    this.pollStationService();  // Avoid waiting for the first interval.
    this.pollingJob = setInterval(() => this.pollStationService(), 250);
  }

  // TODO(jethier): Update this service to use pubsub instead of polling.
  /**
   * Make a request to the frontend server for this station's state.
   */
  pollStationService() {
    // TODO(jethier): Fat arrow syntax below used to make __this unecessary.
    //                Not sure when or why it broke. Investigation needed.
    let __this = this;
    this.stationService.getState(this.ip, this.port)
                  .subscribe(
                      state => __this.updateState(state),
                      error => console.log('Error: ', error));
  }

  /**
   * Use the given station state to update the view component.
   */
  updateState(state) {
    // TODO(jethier): Detect when a new test is being started, display the
    //                previous test, and pause for a countdown.
    if (state && state.framework) {
      this.framework = state.framework;
      if (state.test) { 
        this.test.update(state.test.record);

        // Update the running phase.
        let n = state.test.record.phases.length;
        this.test.updatePhase(n, state.test.running_phase_record);

        // Update pending phases using dummy phase records.
        for (var i = 1; i < state.test.pending_phases.length; i++) {
          this.test.updatePhase(n + i, {
            'name': state.test.pending_phases[i][0],
            'codeinfo': { 'docstring': state.test.pending_phases[i][1] },
            'measurements': []
          });
        }
      }
      else if (this.test.dutID) { this.test = new Test(); }
      this.stationState = state;
      this.lastUpdateTime = Date.now();
    }
  }

  /**
   * Tear down the view component when navigating away.
   */
  ngOnDestroy() {
    clearInterval(this.pollingJob);
  }
}
