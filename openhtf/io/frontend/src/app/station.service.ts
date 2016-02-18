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


import {Injectable}     from 'angular2/core';
import {Headers,
        Http,
        Response,
        RequestOptions} from 'angular2/http';

import {Observable} from 'rxjs/Observable';


/** Provides interactions with OpenHTF stations through their HTTP API's. **/
@Injectable()
export class StationService {
  BASE_URL: string = '/raw/station';

  /**
   * Create a StationService.
   */
  constructor(private http: Http) {
    // TODO(jethier): Get updates from stations through pubsub rather than
    //                through dumb polling.
  }

  /**
   * Extract and return station state from an Observable.
   */
  private extractData(res: Response) {
    if (res.status < 200 || res.status >= 300) {
      throw new Error(`Bad response status from station: ${res.status}`);
    }
    let body = res.json();
    return body;
  }

  /**
   * Log an error message thrown by an Observable and re-throw.
   */
  private handleError(error: any) {
    let errMsg = error.message || 'Error communicating with station.';
    console.error(errMsg);
    return Observable.throw(errMsg);
  }

  /**
   * Return an Observable for the current state of the station.
   */
  getState(ip, port): Observable<StationState> {
    return this.http.get(`${this.BASE_URL}/${ip}/${port}`)
      .map(this.extractData)
      .catch(this.handleError);
  }

  /**
   * Send a response to the given station for the given prompt.
   */
   respondToPrompt(ip: string, port: string, id: string, response: string) {
     let headers = new Headers({ 'Content-Type': 'application/json' });
     let options = new RequestOptions({ headers: headers });
     this.http.post('/station/' + ip + '/' + port + '/prompt/' + id,
       response,
       options).catch(this.handleError)
               .subscribe();
   }
}


/**
 * Thin record class representing a response from an OpenHTF station API.
 */
export class StationState {
  framework: any;
  test: any;
}
