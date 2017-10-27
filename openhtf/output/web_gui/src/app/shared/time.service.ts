/**
 * Service which provides the current time in milliseconds.
 */

import 'rxjs/add/observable/interval';
import 'rxjs/add/operator/map';
import 'rxjs/add/operator/publish';

import { Injectable } from '@angular/core';
import { Observable } from 'rxjs/Observable';

const UPDATE_INTERVAL_MS = 100;

@Injectable()
export class TimeService {
  readonly observable = Observable.interval(UPDATE_INTERVAL_MS)
                            .map(() => {
                              this.last = Date.now();
                              return this.last;
                            })
                            .publish();
  last: number|null = null;

  constructor() {
    this.observable.connect();
  }
}
