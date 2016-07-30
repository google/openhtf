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

import {Component,
        Injectable,
        Input,
        OnInit,
        Pipe,
        PipeTransform} from 'angular2/core';

import {
  StatusToDark,
  StatusToSuperDark,
  FirstEltOrBlank,
  MeasToPassFail,
  ObjectToArray,
  ObjectToUl,
  OutcomeToColor,
  StatusToColor
} from './utils';
import 'file?name=/styles/station.phases.css!./station.phases.css';
import 'file?name=/templates/station.phases.html!./station.phases.html';


/** A pipe to stringify measurement collections into html elements. **/
@Pipe({name: 'measToHtml', pure: false})
export class MeasToHtml implements PipeTransform {
  stringify(measurements: any): string {
    if (measurements == undefined || measurements == null) {
      return '';
    }
    let outcome = 'PASS';
    let result = `
      <table class="measurement-listing white-text">
        <tr class="header-row">
          <td>measurement name</td>
          <td>validator(s)</td>
          <td>value</td>
          <td class="outcome">outcome</td>
        </tr>`;
    Object.keys(measurements).forEach(key => {
      let validators = measurements[key].validators || '';
      let value = measurements[key].measured_value || '';
      if (typeof value == 'object') {
        let new_value = '';
        Object.keys(value).forEach(idx => {
          new_value += `(${value[idx]}), `;
        })
        value = new_value.slice(0, -2);
      }
      let outcome = measurements[key].outcome;
      result += `<tr class="measurement">
          <td class="name">${key}</td>
          <td class="validator">${validators}</td>
          <td class="value">${value}</td>
          <td class="outcome">${outcome}</td>
        </tr>`;
    })
    result += '</table>';
    return result;
  }

  transform(measurements: any): string {
    return this.stringify(measurements);
  }
}


/** The PhaseListing view component. **/
@Component({
  selector: 'phase-listing',
  templateUrl: 'templates/station.phases.html',
  styleUrls: ['styles/station.phases.css'],
  pipes: [StatusToDark,
          StatusToSuperDark,
          FirstEltOrBlank,
          MeasToPassFail,
          MeasToHtml,
          ObjectToArray,
          ObjectToUl,
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
