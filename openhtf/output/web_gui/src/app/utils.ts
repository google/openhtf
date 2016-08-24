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

declare var SockJS; // Global provided by the sockjs library.

import {Injectable, Pipe, PipeTransform} from 'angular2/core';


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
    'WAITING_FOR_TEST_START': 'WAITING',
    'STOP_WAIT': 'WAITING',
    'TIMEOUT': 'ERROR',
    'ABORTED': 'ERROR',
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
    'UNREACHABLE': 'blue-grey lighten-3 white-text',
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

  transform(input: any): any {
    let result = [];
    if (input == undefined || input == null) {
      return result
    }
    let keys = Object.keys(input);
    keys.forEach(key => {
      result.push({ 'key': key, 'value': input[key] });
    });
    return result;
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
  constructor(seconds: number, onDoneCallback: Function) {
    this.lengthSeconds = seconds;
    this.onDone = onDoneCallback || function() { };
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
    this.onDone();
  }

  /**
   * Pause/unpause the countdown.
   */
  pauseOrUnpause() {
    if (this.intervalID) { this.stop(); }
    else { this.start(); }
  }
}


@Injectable()
export class SubscriptionService {
  CONNECTION_TIMEOUT_MS: number = 2000;
  INITIAL_RECONNECT_COUNTDOWN_MS: number = 1000;

  private checkJob: number;
  private gracefullyClosed: boolean;
  private reconnectCountdown: number;
  private reconnectJob: number;
  private sock: any;
  private url: string;

  /**
   * Create a SubscriptionService.
   */
  constructor() {
    this.gracefullyClosed = true;
    this.reconnectCountdown = this.INITIAL_RECONNECT_COUNTDOWN_MS;
    this.url = null;
  }

  /**
   * Set the subscription URL. Must call before subscribing.
   */
  setUrl(newUrl) {
    this.url = newUrl;
  }

  /**
   * Subscribe to the service at this.url via sockjs connection.
   */
  subscribe() {
    if (this.url == null) {
      console.error('Subscription URL must be set before subscribing.');
      return;
    }
    console.debug(`Attempting to subscribe to ${this.url}.`);
    this.sock = SockJS(this.url);
    this.sock.onmessage = (msg) => { this.onmessage(msg); };
    this.sock.onopen = () => { this.handleOpen(); };

    // Check the connnection after the timeout, and reconnect with exponential
    // backoff on failure.
    this.checkJob = setTimeout(() => {
      if (this.sock.readyState != 1) {
        console.debug(`Subscription to ${this.url} failed.`);
        if (this.reconnectCountdown == Infinity) {
          console.warn('Too many failed re-sub attempts; stopping.');
          return;
        }
        console.debug(`Trying again in ${this.reconnectCountdown}ms.`);
        this.reconnectJob = setTimeout(() => {
          this.subscribe();
        }, this.reconnectCountdown);
        this.reconnectCountdown = this.reconnectCountdown * 2;
      }
    }, this.CONNECTION_TIMEOUT_MS);
  }

  /**
   * Callback tied to the socket's onopen condition.
   *
   * Does internal housekeeping in addition to normal onopen behavior.
   */
  handleOpen() {
    console.debug(`Subscribed to ${this.url}.`);
    this.gracefullyClosed = false;
    this.reconnectCountdown = this.INITIAL_RECONNECT_COUNTDOWN_MS;
    this.sock.onclose = () => this.handleClose();
    this.onsubscribe();
  }

  /**
   * Callback tied to socket's onclose condition, only if socket was opened.
   *
   * In addition to normal onclose behavior, will initiate reconnect attempts
   * on non-graceful closure.
   */
  handleClose() {
    this.onunsubscribe();
    if (!this.gracefullyClosed) {
      console.debug(`Connection to ${this.url} lost. Will attempt re-sub.`);
      this.subscribe();
    }
  }

  /**
   * Intentionally closes the socket.
   */
  unsubscribe() {
    console.debug(`Unsubscribing from ${this.url}.`);
    if (this.reconnectJob) {
      clearTimeout(this.reconnectJob);
    }
    if (this.checkJob) {
      clearTimeout(this.checkJob);
    }
    this.gracefullyClosed = true;
    this.sock.close();
  }

  //  -------- API methods. Subclasses should override. --------

  /**
   * Called when subscription is successfully made.
   */
  onsubscribe() {}

  /**
   * Called when an active subscription is closed.
   */
  onunsubscribe() {}

  /**
   * Called when messages are recived, with the message.
   */
  onmessage(message: any) {}
}
