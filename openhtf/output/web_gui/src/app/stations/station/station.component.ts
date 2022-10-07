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
 * Component representing a station.
 */

import { Component, EventEmitter, Input, OnDestroy, OnInit, Output } from '@angular/core';

import { ConfigService } from '../../core/config.service';
import { Station } from '../../shared/models/station.model';
import { TestState } from '../../shared/models/test-state.model';

import { StationService } from './station.service';

export class StationDeselectedEvent {}

const subscriptionRetryMs = 200;
const subscriptionRetryBackoff = 1.08;
const subscriptionRetryMax = 1500;

@Component({
  selector: 'htf-station',
  templateUrl: './station.component.html',
  styleUrls: ['./station.component.scss'],
})
export class StationComponent implements OnDestroy, OnInit {
  @Input() selectedStation: Station;
  @Output() onDeselectStation = new EventEmitter<StationDeselectedEvent>();

  selectedTest: TestState|null = null;  // Selected in the history.

  constructor(
      private stationService: StationService, private config: ConfigService) {}

  get activeTest(): TestState|null {
    if (this.selectedTest !== null) {
      return this.selectedTest;
    }
    return this.stationService.getTest(this.selectedStation);
  }

  get dashboardEnabled() {
    return this.config.dashboardEnabled;
  }

  get hasError() {
    return this.stationService.hasError;
  }

  get isLoading() {
    return this.stationService.isSubscribing;
  }

  get isOnline() {
    return !(this.hasError || this.isLoading);
  }

  ngOnInit() {
    this.stationService.subscribe(
        this.selectedStation, subscriptionRetryMs, subscriptionRetryBackoff,
        subscriptionRetryMax);
  }

  ngOnDestroy() {
    this.stationService.unsubscribe();
  }

  goBack() {
    this.onDeselectStation.emit(new StationDeselectedEvent());
  }

  manualReload() {
    this.stationService.refresh();
  }

  onSelectTest(test: TestState) {
    this.selectedTest = test;
  }
}
