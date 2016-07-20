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

declare var jsonpatch; // Global provided by the fast-json-patch package.

import {Injectable} from 'angular2/core';

import {SubscriptionService} from './utils';


/** Provider of Dashboard updates from the OpenHTF frontend server. **/
@Injectable()
export class DashboardService extends SubscriptionService {
  URL: string = '/sub/dashboard';

  private dashMap: any;
  private listings: any[];

  /**
   * Create a DashboardService.
   */
  constructor() {
    super();
    this.dashMap = {}; // Because we want persistent records.
    this.listings = []; // Because ngFor only takes lists.
    this.setUrl(this.URL);
  }

  /**
   * Parse the server's messages and update state accordingly.
   * @param message - A JSON dashboard state from the frontend server.
   */
  updateListings(message: any) {
    for (var key in message) {
      if (this.dashMap[key] == undefined) {
        this.dashMap[key] = message[key];
        this.listings.push(message[key]);
      }
      else {
        let diff = jsonpatch.compare(this.dashMap[key], message[key]);
        jsonpatch.apply(this.dashMap[key], diff);
      }
    }
  }

  /**
   * Return the current dashboard listing.
   */
  getListings() {
    return this.listings;
  }

  /**
   * Open the sockjs connection. Attempt to reconnect after timeout.
   */
  onmessage(msg) {
    this.updateListings(JSON.parse(msg.data));
  }
}
