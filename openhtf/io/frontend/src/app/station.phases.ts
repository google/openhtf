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

import {Component, Input}               from 'angular2/core';
import {OnInit}                         from 'angular2/core';

import {Phase}            from './test';
import {StatusToColor,
        ColorToDark,
        ColorToSuperDark,
        OutcomeToColor}   from './utils';

import 'file?name=/templates/station.phases.html!./station.phases.html';
import 'file?name=/styles/station.phases.css!./station.phases.css';


/** The PhaseListing view component. **/
@Component({
  selector: 'phases',
  templateUrl: 'templates/station.phases.html',
  styleUrls: ['styles/station.phases.css'],
  pipes: [StatusToColor, ColorToDark, ColorToSuperDark, OutcomeToColor]
})
export class PhaseListing implements OnInit {
  @Input() phases: Phase[];

  /**
   * Set up the view component.
   */
  public ngOnInit(): any {
    // Enable materialize-css js support for collapsibles.
    $('.collapsible').collapsible({});
  }
}
