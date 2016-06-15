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

import {
  StatusToDark,
  StatusToSuperDark,
  FirstEltOrBlank,
  MeasToPassFail,
  ObjectToArray,
  OutcomeToColor,
  StatusToColor
} from './utils';
import 'file?name=/styles/station.phases.css!./station.phases.css';
import 'file?name=/templates/station.phases.html!./station.phases.html';


/** The PhaseListing view component. **/
@Component({
  selector: 'phase-listing',
  templateUrl: 'templates/station.phases.html',
  styleUrls: ['styles/station.phases.css'],
  pipes: [StatusToDark,
          StatusToSuperDark,
          FirstEltOrBlank,
          MeasToPassFail,
          ObjectToArray,
          OutcomeToColor,
          StatusToColor,]
})
export class PhaseListing implements OnInit {
  @Input() state;
  @Input() currentMillis;

  /**
   * Set up the view component.
   */
  public ngOnInit(): any {
    // Enable materialize-css js support for collapsibles.
    $('.collapsible').collapsible({});
  }
}
