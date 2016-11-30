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


declare var jsonpatch; // Global provided by the fast-json-patch package.

import {Injectable} from 'angular2/core';
import {Headers, Http, RequestOptions} from 'angular2/http';
import {Observable} from 'rxjs/Observable';
import 'rxjs/add/observable/throw';
import 'rxjs/add/operator/catch';

import {SubscriptionService} from './utils';


/** Provider of station updates from the OpenHTF frontend server. **/
@Injectable()
export class StationService extends SubscriptionService {
  BASE_URL: string = '/sub/station';
  UNKNOWN_HOST: string = '???.???.???.???';
  UNKNOWN_PORT: string = '????';
  UNKNOWN_STATION_ID: string = '(station ID unknown)';

  private history: any;
  private reachable: boolean;
  private stationInfo: any;
  private testUIDs: string[];
  private tests: any;
  private pausedTests: any[];

  /**
   * Create a StationService.
   */
  constructor(private http: Http) {
    super();
    this.history = {};
    this.reachable = false;
    this.stationInfo = {
      'host': this.UNKNOWN_HOST,
      'port': this.UNKNOWN_PORT,
      'station_id': this.UNKNOWN_STATION_ID
    };
    this.testUIDs = [];
    this.tests = {};
    this.pausedTests = [];
  }

  /**
   * Configure the station service; must be done once before subscribing.
   * @param host - Host of the OpenHTF station to get updates for.
   * @param port - Port for the OpenHTF station's station API.
   */
  setHostPort(host: string, port: string) {
    this.stationInfo.host = host;
    this.stationInfo.port = port;
    this.setUrl(`${this.BASE_URL}?host=${host}&port=${port}`);
  }

  /**
   * Update our state object for the given test to match the provided state.
   * @param test_uid - A string uniquely identifying a test on the station.
   * @param state - An object representing a serialized OpenHTF RemoteState
   *                instance.
   */
  updateTest(test_uid: string, state: any) {
    if (this.tests[test_uid] == undefined) {
      this.tests[test_uid] = state;
      this.testUIDs.push(test_uid);
    } else if (this.pausedTests.indexOf(test_uid) == -1) {
      let diff = jsonpatch.compare(this.tests[test_uid], state);
      jsonpatch.apply(this.tests[test_uid], diff);
      if (state && state.status == 'COMPLETED') {
        // Test has finished!
        // TODO(jethier): Refresh the history object.
        this.pausedTests.push(test_uid);
        console.debug('Test completed.');
        setTimeout(() => {
          this.pausedTests.splice(this.pausedTests.indexOf(test_uid), 1);
        }, 15000);
      }
    }
  }

  /**
   * Process messages upon receipt.
   * @param msg - A JSON-formatted representation of a test update. Contains
   *              two top-level fields:
   *                  test_uid: A string uniquely identifying the test.
   *                  state: A serialized OpenHTF RemoteState instance.
   */
  onmessage(msg) {
    this.reachable = true;
    let parsedData = JSON.parse(msg.data);
    let test_uid = parsedData.test_uid;
    let state = parsedData.state;
    if (!state) {
      console.warn('Received an empty state update.');
      return;
    }
    if (this.stationInfo.station_id != state.test_record.station_id) {
      if (this.stationInfo.station_id == this.UNKNOWN_STATION_ID) {
        this.stationInfo.station_id = state.test_record.station_id;
      } else {
        console.warn(
            `Received a station_id that doesn't match the previous one: ` +
            `${state.test_record.station_id}.`);
      }
    }
    this.updateTest(test_uid, state);
  }

  onunsubscribe() {
    this.reachable = false;
  }

  /**
   * Return a reference to the basic info about the station.
   *
   * The returned object contains the following fields:
   *     host: A string host (ip address) for the station.
   *     port: A string TCP port for the station's API.
   *     station_id: A string OpenHTF station_id.
   */
  getStationInfo(): Object {
    return this.stationInfo;
  }

  /**
   * Return a reference to the object representing the tests on this station.
   *
   * The returned object maps string unique id's for each test on the station
   * to objects representing the serialized OpenHTF RemoteState instances.
   */
  getTests(): any[] {
    return this.tests;
  }

  /**
   * Return a reference to the array listing test UIDs on this station.
   *
   * The UIDs are listed in the order that they were first seen.
   */
  getTestUIDs(): any[] {
    return this.testUIDs;
  }

  /**
   * Log an error message thrown by an Observable and re-throw.
   */
  private handleError(error: any) {
    let errMsg = error.message || 'Error communicating with station.';
    return Observable.throw(errMsg);
  }

  /**
   * Send a response to the given station for the given prompt ID.
   */
  respondToPrompt(ip: string, port: string, test_uid: number, id: string, response: string) {
    let headers = new Headers({ 'Content-Type': 'application/json' });
    let options = new RequestOptions({ headers: headers });
    let plug_url = `/plugs/${ ip }/${ port }/${ test_uid }/openhtf.plugs.user_input.UserInput`;
    let payload = JSON.stringify({
      method: 'respond',
      args: [id, response],
    });
    this.http.post(plug_url, payload, options)
        .catch(this.handleError)
        .subscribe();
  }
}
