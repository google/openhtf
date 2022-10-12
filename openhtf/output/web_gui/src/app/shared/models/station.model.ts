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
 * Summary info about a station.
 */

export enum StationStatus {
  online = 9,
  unreachable,
}

export class Station {
  cell: string|null;
  host: string;
  hostPort: string;  // Used to uniquely identify stations.
  label: string;
  port: string;
  stationId: string;
  status: StationStatus;
  testDescription: string|null;
  testName: string|null;

  // Using the class as the interface for its own constructor allows us to call
  // the constructor in named-argument style.
  constructor(params: Station) {
    Object.assign(this, params);
  }
}
