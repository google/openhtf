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


import {Pipe, PipeTransform} from 'angular2/core';


/** A base class for map-based piping. Subclasses need to override 'map'.**/
export class MapPipe implements PipeTransform {
  map = {}

  /**
   * Return the mapped string for the given input string.
   */
  transform(input: string): string {
    if (this.map[input]) {
      return this.map[input];
    }
    return input;
  }
}


/** A Pipe for condensing status codes down to a simpler set.**/
@Pipe({ name: 'simplifyStatus' })
export class SimplifyStatus extends MapPipe {
  map = {
    'EXECUTING': 'RUNNING',
    'START_WAIT': 'WAITING',
    'STOP_WAIT': 'WAITING',
    'TIMEOUT': 'ERROR',
  };
}


/** A Pipe for turning status codes into materialize-css color classes.**/
@Pipe({name: 'statusToColor'})
export class StatusToColor extends MapPipe {
  map = {
    'RUNNING': 'blue lighten-1 white-text',
    'ONLINE': 'blue lighten-1 white-text',
    'PASS': 'green lighten-1 white-text',
    'FAIL': 'red lighten-1 white-text',
    'ERROR': 'yellow darken-3 white-text',
    'PENDING': 'blue-grey lighten-3 white-text',
    'WAITING': 'blue-grey lighten-3 white-text',
    'OFFLINE': 'blue-grey lighten-3 white-text',
  };
}


/** A Pipe for darkening status colors. **/
@Pipe({name: 'statusToDark'})
export class StatusToDark extends MapPipe {
  map = {
    'RUNNING': 'blue darken-2 white-text',
    'ONLINE': 'blue darken-2 white-text',
    'PASS': 'green darken-2 white-text',
    'FAIL': 'red darken-2 white-text',
    'ERROR': 'yellow darken-4 white-text',
    'PENDING': 'blue-grey lighten-2 white-text',
    'WAITING': 'blue-grey lighten-2 white-text',
    'OFFLINE': 'blue-grey lighten-2 white-text',
  };
}


/** A Pipe for darkening status colors even more. **/
@Pipe({ name: 'statusToSuperDark' })
export class StatusToSuperDark extends MapPipe {
  map = {
    'RUNNING': 'blue darken-4 white-text',
    'ONLINE': 'blue darken-4 white-text',
    'PASS': 'green darken-4 white-text',
    'FAIL': 'red darken-4 white-text',
    'ERROR': 'yellow darken-5 white-text',
    'PENDING': 'blue-grey lighten-1 white-text',
    'WAITING': 'blue-grey lighten-1 white-text',
    'OFFLINE': 'blue-grey lighten-1 white-text',
  };
}


/** A Pipe for turning outcome codes into materialize-css color classes.**/
@Pipe({ name: 'outcomeToColor' })
export class OutcomeToColor extends MapPipe {
  map = {
    'PASS': 'green-text text-lighten-4',
    'FAIL': 'red-text text-lighten-4',
    'UNSET': 'blue-grey-text text-lighten-4'
  };
}


/** A Pipe for colorizing log entries based on logging level. **/
@Pipe({name: 'loggingLevelToColor'})
export class LoggingLevelToColor extends MapPipe {
  map = {
    0: 'blue-text text-lighten-1',   // NOTSET
    10: 'blue-text text-lighten-1',   // DEBUG
    20: 'blue-text text-lighten-1',   // INFO
    30: 'yellow-text text-darken-4',  // WARNING
    40: 'red-text text-lighten-1',    // ERROR
    50: 'red-text text-lighten-1'     // CRITICAL
  };
}


/** A pipe for turning an Object into something Angular2 can loop over. **/
@Pipe({name: 'objectToArray', pure: false})
export class ObjectToArray implements PipeTransform {
  result: any[];

  transform(input: any): any {
    this.result = [];
    if (input == undefined || input == null) {
      return this.result
    }
    let keys = Object.keys(input);
    keys.forEach(key => {
      this.result.push({ 'key': key, 'value': input[key] });
    });
    return this.result;
  }
}


/** A pipe to recurisely stringify objects into html <ul> elements. **/
@Pipe({name: 'objectToUl', pure: false})
export class ObjectToUl implements PipeTransform {
  ulify(object: any): string {
    if (object == undefined || object == null) {
      return '';
    }
    let result = '<ul>';
    Object.keys(object).forEach(key => {
      result += `<li><span class="key">${key}:&nbsp;</span><span class="value">`;
      if (typeof object[key] == 'object') {
        result += this.ulify(object[key]);
      }
      else {
        result += object[key];
      }
      result += '</span></li>';
    })
    result += '</ul>';
    return result;
  }

  transform(object: any): string {
    return this.ulify(object);
  }
}


/** A pipe for reducing a collection of measurements to a pass/fail result. **/
@Pipe({name: 'measToPassFail'})
export class MeasToPassFail implements PipeTransform {
  transform(measurements: any): string {
    let result = 'PASS'
    Object.keys(measurements).forEach(key => {
      if (measurements[key].outcome != 'PASS') {
        result = 'FAIL';
      }
    })
    return result;
  }
}


/** A pipe for getting the first element of an array that only might exist. **/
@Pipe({name: 'firstEltOrBlank'})
export class FirstEltOrBlank implements PipeTransform {
  /**
   * Return the first element of the array if possible, or the empty string.
   */
  transform(input: any): string {
    if (input && input.length > 0) {
      return input[0];
    }
    return '';
  }
}


/** Generic countdown timer. **/
export class Countdown {
  intervalID: number;
  lengthSeconds: number;
  millisRemaining: number = 0;
  onDone: Function;

  /**
   * Create a new Countdown for the given number of seconds.
   * @param {number} seconds - Length of the countdown in seconds.
   */
  constructor(seconds: number) {
    this.lengthSeconds = seconds;
    this.onDone = function() { };
    this.reset();
  }

  /**
   * Reset the countdown.
   */
  reset() {
    this.millisRemaining = (1000 * this.lengthSeconds);
  }

  /**
   * Start the countdown.
   */
  start() {
    var lastCheck = Date.now();
    this.intervalID = setInterval(() => {
      this.millisRemaining -= (Date.now() - lastCheck);
      if (this.millisRemaining <= 0) {
        this.millisRemaining = 0;
        this.stop();
        this.onDone();
      }
      else { lastCheck = Date.now(); }
    }, 250);
  }

  /**
   * Stop the countdown.
   */
  stop() {
    clearInterval(this.intervalID);
    this.intervalID = undefined;
  }

  /**
   * Pause/unpause the countdown.
   */
  pauseOrUnpause() {
    if (this.intervalID) { this.stop(); }
    else { this.start(); }
  }
}
