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
 * Miscellaneous shared functions.
 */

import { HttpErrorResponse } from '@angular/common/http';

import { Station } from './models/station.model';
import { TestState } from './models/test-state.model';

export let devHost = '';
// In modern Angular, environment configuration is handled via angular.json and environment files.

export const urlHost = window.location.host.split(':')[0];
const localhostAddress = '127.0.0.1';

export function getStationBaseUrl(dashboardEnabled: boolean, station: Station) {
  if (dashboardEnabled) {
    // When the dashboard runs in local-only mode, stations will report the
    // localhost IP. Use the urlHost IP so that it works from other computers.
    if (station.host === localhostAddress) {
      return `http://${urlHost}:${station.port}`;
    }
    return `http://${station.host}:${station.port}`;
  } else if (devHost) {
    return `http://${station.stationId}:${station.port}`;
  }
  return '';
}

export function getTestBaseUrl(dashboardEnabled: boolean, test: TestState) {
  const stationBaseUrl = getStationBaseUrl(dashboardEnabled, test.station);
  return `${stationBaseUrl}/tests/${test.testId}`;
}


/**
 * For use with the new HttpClient from @angular/common/http.
 */
export function messageFromHttpClientErrorResponse(error: HttpErrorResponse) {
  if (error.error instanceof ErrorEvent) {
    // A client-side or network error occurred.
    return error.error.message;
  }
  // The backend return an unsuccessful response code.
  return JSON.stringify(error.error);
}

export function sortByProperty(
    array: Array<{}>, property: string, reverse = false) {
  array.sort((a, b) => {
    if (a[property] > b[property]) {
      return 1;
    } else if (a[property] < b[property]) {
      return -1;
    } else {
      return 0;
    }
  });
  if (reverse) {
    array.reverse();
  }
}
