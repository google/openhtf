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


import {Injectable} from 'angular2/core';
import {Http, Response} from 'angular2/http';
import 'rxjs/Rx';


/** Provider of Dashboard updates from the OpenHTF frontend server. **/
@Injectable()
export class DashboardService {
  POLLING_INTERVAL_MS: number = 3000;
  URL: string = '/raw/dashboard';

  listings: Listing[];
  dashMap: {};
  server: any;
  polling_job: number;

  /**
   * Create a DashboardService.
   */
  constructor(private http: Http) {
    this.listings = []; // Because ngFor only takes lists.
    this.dashMap = {}; // Because we want persistent records.
    this.start();
  }

  /**
   * Start polling the frontend server for dashboard updates.
   */
  start() {
    this.requestListings(); // Avoid waiting for the first poll interval.
    this.polling_job = setInterval(() => {
      this.requestListings();
    }, this.POLLING_INTERVAL_MS);
  }

  /**
   * Stop polling for dashboard updates.
   */
  stop() {
    clearInterval(this.polling_job);
  }

  /**
   * Make an HTTP request for dashboard listings from the frontend server.
   */
  requestListings() {
    this.http.get(this.URL)
      .map(res => res.json())
      .subscribe(
        data => this.updateListings(data),
        err => console.log('Error: ' + err)
      );
  }

  /**
   * Parse the server's response and update state accordingly.
   * @param data - A JSON dashboard response from the frontend server.
   */
  updateListings(data: any) {
    for (var key in data) {
      if (this.dashMap[key] === undefined) {
        this.dashMap[key] = new Listing(data[key]);
        this.listings.push(this.dashMap[key]);
      }
      else {
        this.dashMap[key].update(data[key]);
      }
    }
  }

  /*
   * Return the current dashboard listing.
   */
  getListings() {
    return this.listings;
  }
}


/** Data class representing a single known station. **/
export class Listing {
  name: string;
  ip: string;
  port: number;
  status: string;
  starred: boolean;

  /**
   * Create a Listing from a JSON object.
   */
  constructor(jsonData) {
    this.update(jsonData)
    this.starred = false;
  }

  /**
   * Update a Listing from a JSON object.
   *
   * The JSON object passed in should have the following structure:
   *   * station_id: string
   *   * hostport: [host: string, port: number]
   *   * status: string
   */
  update(jsonData: any) {
    this.name = jsonData['station_id'];
    this.ip = jsonData['hostport'][0];
    this.port = jsonData['hostport'][1];
    this.status = jsonData['status'];
  }
}
