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

import {Component, Input, OnDestroy, OnInit} from 'angular2/core';
import {RouterLink} from 'angular2/router';

import {DashboardService} from './dashboard.service';
import {Countdown, StatusToColor} from './utils';
import 'file?name=/styles/dashboard.css!./dashboard.css';


/** StationCard component. **/
@Component({
  selector: 'station-card',
  template: `
    <a class="waves-effect waves-light card hoverable
              {{listing.status | statusToColor}}"
              [routerLink]="['Station', {host:listing.host,
                                         port:listing.port}]">
        <div class="station-name">{{listing.station_id}}</div>
        <div class="details">
          {{listing.host}} : {{listing.port}}
       </div>
       <div class="cardfooter">
         <div class="leftcell">
           <span *ngIf="listing.status == 'UNREACHABLE'"
                 class="unreachable-label">
             <span class="iconlabel">
               <i class="tiny material-icons">error_outline</i>
               <span>{{listing.status}}</span>
             </span>
           </span >
         </div>
         <div class="rightcell">
           <span class="star">
             <i class="small material-icons">computer</i>
           </span>
         </div>
       </div>
    </a>
  `,
  directives: [RouterLink],
  styleUrls: ['styles/dashboard.css'],
  pipes: [StatusToColor]
})
export class StationCard {
  @Input() listing;
}


/** Dashboard component. **/
@Component({
  selector: 'dashboard',
  template: `
    <div id="dashboard">
      <div *ngIf="dashboardService.getListings().length == 0"
           class="big-message">
          No stations detected.
      </div>
      <station-card *ngFor="let listing of dashboardService.getListings()"
                    [listing]="listing">
      </station-card>
    </div>
  `,
  styleUrls: ['styles/dashboard.css'],
  directives: [StationCard],
  providers: [DashboardService],
})
export class Dashboard implements OnDestroy, OnInit {

  /**
   * Create a Dashboard component.
   */
  constructor(private dashboardService: DashboardService) {}

  /**
   * Set up the component by subscribing to dashboard updates.
   */
  ngOnInit() {
    this.dashboardService.subscribe();
  }

  /**
   * Tear down the component by closing the dashboard service.
   */
   ngOnDestroy() {
     this.dashboardService.unsubscribe();
   }
}
