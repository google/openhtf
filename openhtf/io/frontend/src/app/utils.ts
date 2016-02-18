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


// TODO(jethier): Clean up all these maps, maybe using inheritance. They are
//                all doing the same type of operation, just on different data.

/** A Pipe for turning status codes into materialize-css color classes.**/
@Pipe({name: 'statusToColor'})
export class StatusToColor implements PipeTransform {
  statusMap = {
    'RUNNING': 'blue lighten-1 white-text',
    'EXECUTING': 'blue lighten-1 white-text',
    'ONLINE':  'blue lighten-1 white-text',
    'PASS':    'green lighten-1 white-text',
    'FAIL':    'red lighten-1 white-text',
    'ERROR':   'yellow darken-3 white-text',
    'PENDING': 'blue-grey lighten-3 white-text',
    'START_WAIT': 'blue-grey lighten-3 white-text',
    'STOP_WAIT': 'blue-grey lighten-3 white-text',
    'OFFLINE': 'blue-grey lighten-3 white-text',
  };

  /**
   * Return a materialize-css color class string for the given status code.
   * @param {string} status - A string representing a status code.
   * @return {string} A string of materialize-css color classes.
   */
  transform(status: string) : string {
    return this.statusMap[status]; 
  }
}


/** A Pipe for darkening status colors. **/
@Pipe({name: 'colorToDark'})
export class ColorToDark implements PipeTransform {
  darkStatusMap = {
    'blue lighten-1 white-text':      'blue darken-2 white-text',
    'green lighten-1 white-text':     'green darken-2 white-text',
    'red lighten-1 white-text':       'red darken-2 white-text',
    'yellow darken-3 white-text':     'yellow darken-4 white-text',
    'blue-grey lighten-3 white-text': 'blue-grey lighten-2 white-text'
  };

  /**
   * Return darker versions of the given status color classes.
   * @param {string} color - materialize-css color classes for a status.
   * @return {string} Darker versions of the given color classes.
   */
  transform(color: string) : string {
    return this.darkStatusMap[color];
  }
}


/** A Pipe for darkening status colors even more. **/
@Pipe({ name: 'colorToSuperDark' })
export class ColorToSuperDark implements PipeTransform {
  darkerStatusMap = {
    'blue lighten-1 white-text': 'blue darken-4 white-text',
    'green lighten-1 white-text': 'green darken-4 white-text',
    'red lighten-1 white-text': 'red darken-4 white-text',
    'yellow darken-3 white-text': 'yellow darken-5 white-text',
    'blue-grey lighten-3 white-text': 'blue-grey lighten-1 white-text'
  };

  /**
   * Return darkest versions of the given status color classes.
   * @param {string} color - materialize-css color classes for a status.
   * @return {string} Darkest versions of the given color classes.
   */
  transform(color: string): string {
    return this.darkerStatusMap[color];
  }
}


/** A Pipe for turning outcome codes into materialize-css color classes.**/
@Pipe({ name: 'outcomeToColor' })
export class OutcomeToColor implements PipeTransform {
  outcomeMap = {
    'PASS': 'green-text text-lighten-4',
    'FAIL': 'red-text text-lighten-4',
    'UNSET': 'blue-grey-text text-lighten-4'
  };

  /**
   * Return a materialize-css color class string for the given outcome code.
   * @param {string} status - A string representing an outcome code.
   * @return {string} A string of materialize-css color classes.
   */
  transform(status: string): string {
    return this.outcomeMap[status];
  }
}


/** A Pipe for colorizing log entries based on logging level. **/
@Pipe({name: 'loggingLevelToColor'})
export class LoggingLevelToColor implements PipeTransform {
  levelMap = {
    0:  'blue-text text-lighten-1',   // NOTSET
    10: 'blue-text text-lighten-1',   // DEBUG
    20: 'blue-text text-lighten-1',   // INFO
    30: 'yellow-text text-darken-4',  // WARNING
    40: 'red-text text-lighten-1',    // ERROR
    50: 'red-text text-lighten-1'     // CRITICAL
  }

  /**
   * Derive materialize-css text-color classes for the given logging level.
   * @param {number} loggingLevel - An integer representing a logging level.
   * @return {string} A string of materialize-css text-color classes.
   */
  transform(loggingLevel: number) : string {
    return this.levelMap[loggingLevel];
  }
}


// TODO(jethier): Switch this to use Angular's built-in date pipe. I didn't
//                realize it existed at the time I wrote this.

/** A Pipe for making epoch time numbers readable and local. **/
@Pipe({ name: 'millisUTCToLocalStr' })
export class MillisUTCToLocalStr implements PipeTransform {
  /** Return a locale-specific string representation of the given time.
   * @param {number} millisUTC - A number of milliseconds since the epoch.
   * @return {string} A locale-specific date and time string.
   */
  transform(millisUTC: number): string {
    return new Date(millisUTC).toLocaleString();
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
