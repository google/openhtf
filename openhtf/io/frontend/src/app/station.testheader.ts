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

import {
  Component,
  Input,
  OnChanges,
  OnInit,
  SimpleChange
} from 'angular2/core';

import {SimplifyStatus, StatusToColor} from './utils';
import 'file?name=/styles/station.testheader.css!./station.testheader.css';
import 'file?name=/templates/station.testheader.html!./station.testheader.html';


/** The TestHeader view component. **/
@Component({
  selector: 'test-header',
  templateUrl: 'templates/station.testheader.html',
  styleUrls: ['styles/station.testheader.css'],
  pipes: [SimplifyStatus, StatusToColor]
})
export class TestHeader implements OnChanges {
  @Input() dutID: string;
  @Input() startTime: number;
  @Input() endTime: number;
  @Input() currentMillis: number;
  @Input() status: string;
  indicatorColorPipe: StatusToColor; // See ngOnChanges.
  indicatorStatusPipe: SimplifyStatus; // See ngOnChanges.

  constructor() {
    this.indicatorColorPipe = new StatusToColor();
    this.indicatorStatusPipe = new SimplifyStatus();
  }

  ngOnInit() {
    $('.test-content').hide()
    setTimeout(() => {
      $('.test-header .tabs').tabs();
      let status = this.indicatorStatusPipe.transform(this.status);
      let color_class = this.indicatorColorPipe.transform(status);
      $('.test-header-nav .indicator').addClass(color_class);
      $('.test-content').show()
    }, 100); // Timing hacks to make materialize-css play nice with Angular2.
  }

  /**
   * Executed when this component's properties change.
   * @param changes - Object describing the changes.
   */
  ngOnChanges(changes: { [propName: string]: SimpleChange }) {
    // The materialize-css "tab" indicator div needs to be colorized to match
    // the test header, and the way we colorize things is by applying classes
    // to tags. The indicator div is not in TestHeader's template, so we find
    // it and apply the right classes to it manually on changes.
    if (changes['status']) {
      let oldStatus = this.indicatorStatusPipe.transform(
          changes['status'].previousValue);
      let newStatus = this.indicatorStatusPipe.transform(
          changes['status'].currentValue);
      $('.test-header-nav .indicator').removeClass(
          this.indicatorColorPipe.transform(oldStatus));
      $('.test-header-nav .indicator').addClass(
        this.indicatorColorPipe.transform(newStatus));
    }
  }
}
