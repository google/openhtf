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

import {Component, Input} from 'angular2/core';
import {RouterLink}       from 'angular2/router';

import {DashboardService,
        Listing}          from './dashboard.service';
import {Countdown}        from './utils'

import {StatusToColor} from './utils';

import 'file?name=/styles/dashboard.css!./dashboard.css';


/** StationCard component. **/
@Component({
  selector: 'station-card',
  template: `
    <a class="waves-effect waves-light card hoverable
              {{listing.status | statusToColor}}"
              [routerLink]="['Station', {ip:listing.ip,
                                         port:listing.port}]">
        <div class="station-name">{{listing.name}}</div>
        <div class="details">
          {{listing.ip}} : {{listing.port}}
       </div>
       <div class="status">{{listing.status}}</div>
    </a>
  `,
  directives: [RouterLink],
  styleUrls: ['styles/dashboard.css'],
  pipes: [StatusToColor]
})
export class StationCard {
  @Input() listing: Listing;
}


/** Dashboard component. **/
@Component({
  selector: 'dashboard',
  template: `
    <div *ngIf="dashboardService.getListings().length == 0">
        no stations detected
    </div>
    <station-card *ngFor="let listing of dashboardService.getListings()"
                  [listing]="listing">
    </station-card>
  `,
  styleUrls: ['styles/dashboard.css'],
  directives: [StationCard],
  providers: [DashboardService],
})
export class Dashboard {

  /**
   * Create a Dashboard component.
   */
  constructor(private dashboardService: DashboardService) {}
}
