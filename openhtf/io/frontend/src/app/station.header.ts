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


declare var $: any;  // Global provided by the jquery package.

import {Component, Input, OnInit} from 'angular2/core';

import {Countdown} from './utils';
import 'file?name=/styles/station.header.css!./station.header.css';
import 'file?name=/templates/station.header.html!./station.header.html';

@Component({
  selector: 'station-header',
  templateUrl: 'templates/station.header.html',
  styleUrls: ['styles/station.header.css']
})
export class StationHeader implements OnInit {
  @Input() countdown: Countdown;
  @Input() stationInfo: any;

  /**
   * Executed when this component's properties change.
   * @param changes - Object describing the changes.
   */
  ngOnInit() {
    $('.navbar .indicator').addClass("blue lighten-1");
    $(".dropdown-button").dropdown();
  }
}
