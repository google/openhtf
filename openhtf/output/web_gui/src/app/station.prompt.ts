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


import {Component, Input} from 'angular2/core';
import {RouteParams} from 'angular2/router';

import {StationService} from './station.service';
import 'file?name=/styles/station.prompt.css!./station.prompt.css';
import 'file?name=/templates/station.prompt.html!./station.prompt.html';

/** Prompt view component. **/
@Component({
  selector: 'prompt',
  templateUrl: 'templates/station.prompt.html',
  styleUrls: ['styles/station.prompt.css'],
  directives: [],
  providers: [StationService]
})
export class Prompt {
  @Input() prompt: any;
  @Input() test_uid: number;

  /**
   * Create a Station view component.
   */
  constructor(private routeParams: RouteParams,
              private stationService: StationService) {
  }

  /**
   * Send the response to the given prompt through the StationService.
   */
  sendResponse(input: HTMLInputElement, id: string) {
    let ip = this.routeParams.get('host');
    let port = this.routeParams.get('port');
    let response = input ? input.value : '';
    this.stationService.respondToPrompt(ip, port, this.test_uid, id, response);
    if (input) {
      input.value = null;
    }
  }
}
