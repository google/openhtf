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

import {Component, Input} from 'angular2/core';
import {RouteParams, Router} from 'angular2/router';
import {Observable} from 'rxjs/Observable';

import {PlugService} from './plug.service';
import 'file?name=/styles/station.prompt.css!./station.prompt.css';
import 'file?name=/templates/station.prompt.html!./station.prompt.html';


/** Prompt view component. **/
@Component({
  selector: 'prompt',
  templateUrl: 'templates/station.prompt.html',
  styleUrls: ['styles/station.prompt.css'],
  directives: [],
  providers: [PlugService]
})
export class Prompt {
  @Input() framework: any;
  private states: any;

  /**
   * Create a Station view component.
   */
  constructor(private routeParams: RouteParams,
              private plugService: PlugService) {
    
  }

  /**
   * Send the response to the given prompt through the StationService.
   */
  sendResponse(input: HTMLInputElement, id) {
<<<<<<< HEAD:openhtf/output/web_gui/src/app/station.prompt.ts
    let ip = this.routeParams.get('ip');
    let port = this.routeParams.get('port');
    let response = input ? input.value : '';
    this.stationService.respondToPrompt(ip, port, id, response);
=======
    let response = input.value || '';
    this.plugService.respondToPrompt(response);
>>>>>>> c35267c... Renamed files:openhtf/io/frontend/src/app/station.prompt.ts
    input.value = null;
  }
  //ngoninit to init the service?? 
  //when to look at the state? do I just put getState() in the html? 
}
