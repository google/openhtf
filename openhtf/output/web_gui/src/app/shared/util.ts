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
import { Response } from '@angular/http';

import { Station } from './models/station.model';
import { TestState } from './models/test-state.model';

// When running a development server, this should be set to point to the
// dashboard server, e.g. `http://localhost:12000`. Otherwise, it should be
// set to the empty string.
export let devHost = '';
if (process.env.ENV !== 'build') {
  devHost = 'http://localhost:12000';
}

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

export function messageFromErrorResponse(error: Response) {
  if (error.status === 0) {
    // The response object probably does not contain useful info.
    return 'The request failed. See the JavaScript console for more info.';
  }
  let errorBody;
  try {
    const errorJson = error.json();
    errorBody = errorJson.error;
  } catch (e) {
    const response = (error as {_body?: string})._body;
    if (response) {
      errorBody = response.replace(/\\"/g, '"');
    } else {
      errorBody = JSON.stringify(error);
    }
  }
  return `${error.status} - ${error.statusText || ''}\n\n${errorBody}`;
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
