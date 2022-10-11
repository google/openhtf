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
 * Maintains info about any known stations.
 */

import { Injectable } from '@angular/core';

import { Station, StationStatus } from '../../shared/models/station.model';
import { SockJsMessage, SockJsService } from '../../shared/sock-js.service';
import { Subscription } from '../../shared/subscription';
import { devHost, urlHost } from '../../shared/util';

const dashboardUrl = `${devHost}/sub/dashboard`;

const dashboardStatusMap = {
  'UNREACHABLE': StationStatus.unreachable,
  'ONLINE': StationStatus.online,
};

/**
 * Raw response types.
 */
interface RawStation {
  cell: string|null;
  host: string;
  port: string;
  station_id: string;
  status: string;
  test_description: string|null;
  test_name: string|null;
}

interface DashboardApiResponse {
  [hostPort: string]: RawStation;
}

/**
 * Parsed response type.
 */
export interface StationMap { [hostPort: string]: Station; }

/**
 * Singleton service used to communicate with the dashboard pub-sub API.
 */
@Injectable()
export class DashboardService extends Subscription {
  readonly stations: StationMap = {};

  constructor(sockJsService: SockJsService) {
    super(sockJsService);
    this.messages.subscribe((message: SockJsMessage) => {
      const response = DashboardService.validateResponse(message.data);
      const newStations = DashboardService.parseResponse(response);
      this.applyResponse(newStations);
    });
  }

  subscribe(
      retryMs: number|null = null, retryBackoff = 1.0,
      retryMax = Number.MAX_VALUE) {
    super.subscribeToUrl(dashboardUrl, retryMs, retryBackoff, retryMax);
  }

  /**
   * Step 1: Validate that a JSON response matches the expected format.
   */
  private static validateResponse(response: {}) {
    // TODO(kenadia): Do validation.
    return response as DashboardApiResponse;
  }

  /**
   * Step 2: Transform a response object into a map of station objects.
   *
   * See StationService.ensureTestList for more information about the decision
   * to separate the API format from the structure of the models used in the
   * frontend.
   */
  private static parseResponse(response: DashboardApiResponse) {
    const newStations: StationMap = {};

    for (const hostPort of Object.keys(response)) {
      const rawStation = response[hostPort];
      newStations[hostPort] = new Station({
        cell: rawStation.cell,
        host: rawStation.host,
        hostPort,
        label: DashboardService.getStationLabel(rawStation),
        port: rawStation.port,
        stationId: rawStation.station_id,
        status: dashboardStatusMap[rawStation.status],
        testDescription: rawStation.test_description,
        testName: rawStation.test_name,
      });
    }

    return newStations;
  }

  /**
   * Step 3: Update our data store with new station information.
   */
  private applyResponse(newStations: StationMap) {
    for (const hostPort of Object.keys(newStations)) {
      const newStation = newStations[hostPort];
      if (hostPort in this.stations) {
        // If a test is not currently running on the station, preserve the
        // information from the seen test.
        if (newStation.cell === null && newStation.testDescription === null &&
            newStation.testName === null) {
          newStation.cell = this.stations[hostPort].cell;
          newStation.label = this.stations[hostPort].label;
          newStation.testDescription = this.stations[hostPort].testDescription;
          newStation.testName = this.stations[hostPort].testName;
        }
        Object.assign(this.stations[hostPort], newStation);
      } else {
        this.stations[hostPort] = newStation;
      }
    }

    // Remove stations no longer reported by the server.
    for (const hostPort of Object.keys(this.stations)) {
      if (!(hostPort in newStations)) {
        delete this.stations[hostPort];
      }
    }
  }

  private static getStationLabel(rawStation: RawStation) {
    if (rawStation.cell) {
      return rawStation.cell;
    }
    if (rawStation.test_name) {
      if (urlHost === rawStation.host || urlHost === rawStation.station_id) {
        return rawStation.test_name;
      }
      return `${rawStation.test_name} on ${rawStation.station_id}`;
    }
    return rawStation.station_id;
  }
}
