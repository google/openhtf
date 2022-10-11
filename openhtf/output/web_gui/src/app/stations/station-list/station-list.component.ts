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
 * Component displaying a list of known test stations.
 */

import { Component, EventEmitter, Input, OnDestroy, OnInit, Output } from '@angular/core';

import { ConfigService } from '../../core/config.service';
import { Station, StationStatus } from '../../shared/models/station.model';
import { TimeService } from '../../shared/time.service';

import { DashboardService } from './dashboard.service';

const subscriptionRetryMs = 200;
const subscriptionRetryBackoff = 1.5;
const subscriptionRetryMax = 1500;

// Emitted by the component when a new selection is made.
export class StationSelectedEvent {
  constructor(public station: Station) {}
}

@Component({
  selector: 'htf-station-list',
  templateUrl: './station-list.component.html',
  styleUrls: ['./station-list.component.scss'],
})
export class StationListComponent implements OnDestroy, OnInit {
  @Input() selectedStation: Station|null;
  @Output() onSelectStation = new EventEmitter<StationSelectedEvent>();

  readonly retryCountdown = this.time.observable.map(currentMillis => {
    const remainingMs = this.dashboard.retryTimeMs - currentMillis;
    const remainingS = Math.round(remainingMs / 1000);
    return `Retrying in ${remainingS}s.`;
  });
  readonly stations: {[hostPort: string]: Station};

  constructor(
      private dashboard: DashboardService, private time: TimeService,
      config: ConfigService) {
    this.stations = dashboard.stations;

    // If the dashboard is disabled, select the station automatically.
    if (!config.dashboardEnabled) {
      const subscription = dashboard.messages.subscribe(() => {
        for (const hostPort of Object.keys(this.stations)) {
          this.select(this.stations[hostPort]);
          // Cancel the subscription once a station has been seen.
          subscription.unsubscribe();
          break;
        }
      });
    }
  }

  get anyStationFound() {
    return Object.keys(this.stations).length > 0;
  }

  get hasError() {
    return this.dashboard.hasError;
  }

  get isLoading() {
    return this.dashboard.isSubscribing;
  }

  get stationCount() {
    return Object.keys(this.stations).length;
  }

  ngOnInit() {
    this.dashboard.subscribe(
        subscriptionRetryMs, subscriptionRetryBackoff, subscriptionRetryMax);
  }

  ngOnDestroy() {
    this.dashboard.unsubscribe();
  }

  isReachable(station: Station) {
    return station.status !== StationStatus.unreachable;
  }

  select(station: Station) {
    this.onSelectStation.emit(new StationSelectedEvent(station));
  }

  // After the stations have failed to load, force a retry.
  manualRetry() {
    this.dashboard.retryNow();
  }

  // After the stations have successfully loaded, force a refresh.
  manualReload() {
    this.dashboard.refresh();
  }
}
