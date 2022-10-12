/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * Maintains info about tests on each station.
 */

import 'rxjs/add/observable/fromPromise';
import 'rxjs/add/observable/of';
import 'rxjs/add/operator/catch';
import 'rxjs/add/operator/mergeMap';

import { Injectable } from '@angular/core';
import { Http, Response } from '@angular/http';
import { Observable } from 'rxjs/Observable';

import { ConfigService } from '../../core/config.service';
import { FlashMessageService } from '../../core/flash-message.service';
import { Phase } from '../../shared/models/phase.model';
import { Station } from '../../shared/models/station.model';
import { TestState, TestStatus } from '../../shared/models/test-state.model';
import { SockJsMessage, SockJsService } from '../../shared/sock-js.service';
import { Subscription } from '../../shared/subscription';
import { getStationBaseUrl, getTestBaseUrl, messageFromErrorResponse } from '../../shared/util';

import { HistoryService } from './history.service';
import { makePhaseFromDescriptor, makeTest, RawTestState } from './station-data';

interface StationApiResponse {
  test_uid?: string;     // Present on messages of type 'update'.
  state?: RawTestState;  // Present on messages of type 'update'.
  type: 'update'|'record';
}

/**
 * Singleton service used to communicate with the station pub-sub API.
 *
 * The service may subscribe to the updates of up to one station at a time.
 */
@Injectable()
export class StationService extends Subscription {
  private readonly phaseDescriptorPromise:
      {[testId: string]: Promise<Phase[]>} = {};
  private readonly testsById: {[testId: string]: TestState} = {};
  private readonly testsByStation: {[stationHostPort: string]: TestState} = {};
  private messagesSubscription = null;

  constructor(
      private config: ConfigService, private flashMessage: FlashMessageService,
      private historyService: HistoryService, private http: Http,
      sockJsService: SockJsService) {
    super(sockJsService);
  }

  subscribe(
      station: Station, retryMs: number|null = null, retryBackoff = 1.0,
      retryMax = Number.MAX_VALUE) {
    if (this.messagesSubscription !== null) {
      this.messagesSubscription.unsubscribe();
    }
    this.messagesSubscription =
        this.messages
            // Use mergeMap since this.applyPhaseDescriptors returns Observable.
            .mergeMap((message: SockJsMessage) => {
              const response = StationService.validateResponse(message.data);
              console.debug('StationService received response:', response);
              const test = this.parseResponse(response, station);
              return this.applyPhaseDescriptors(test);
            })
            .subscribe(test => {
              this.applyResponse(test, station);
            });

    const baseUrl = getStationBaseUrl(this.config.dashboardEnabled, station);
    const stationUrl = `${baseUrl}/sub/station`;
    super.subscribeToUrl(stationUrl, retryMs, retryBackoff, retryMax);
  }

  getTest(station: Station) {
    return this.testsByStation[station.hostPort] || null;
  }

  /**
   * Step 1: Validate that a JSON response matches the expected format.
   */
  private static validateResponse(response: {}) {
    // TODO(kenadia): Do validation.
    return response as StationApiResponse;
  }

  /**
   * Step 2: Transform a response object into a test state object.
   *
   * In OpenHTF's built-in frontend, the test state is passed around frontend
   * templates in the same structure with which it was received, so that the
   * object's structure mimics as much as possible the structure of state
   * objects on the backend. Displaying the state on the frontend thus requires
   * complex templates and pipe functions.
   *
   * Here we adopt a different philosophy. We define distinct interfaces for the
   * API response and the test state used by the frontend. By decoupling the two
   * we can minimize the work done by the templates and we can handle changes to
   * the station API without having to modify the templates.
   */
  private parseResponse(response: StationApiResponse, station: Station) {
    const testState =
        makeTest(response.state, response.test_uid, null, station);
    if (response.type === 'record') {
      this.historyService.prependItemFromTestState(station, testState);
    }
    return testState;
  }

  /**
   * Step 3: Construct the full phase list using the phase descriptors.
   *
   * The test state only includes executed and executing phases, whereas the
   * phase descriptors include all phases. We use the descriptors to extend the
   * test state phase list with the phases which are waiting to be executed.
   *
   * Since this step may require another HTTP request, we return an Observable.
   */
  private applyPhaseDescriptors(test: TestState) {
    return this.getOrRequestPhaseDescriptors(test)
        .map((descriptors: Phase[]) => {
          // Counts all phases that have started execution.
          const numExecutedPhases = test.phases.length;

          if (numExecutedPhases === 0) {
            test.phases.push(...descriptors);
            return test;
          }

          // Find the cutoff point in the list of phase descriptors. We do this
          // by finding the last executed phase that can be matched to a phase
          // descriptor. Normally this is simply the last executed phase,
          // however, if we are currently running a teardown phase, it will not
          // have a corresponding phase descriptor. Therefore, we iterate
          // backwards through the list of executed phases.
          let lastExecutedPhaseIndex = numExecutedPhases - 1;
          let lastExecutedDescriptorIndex = -1;
          while (lastExecutedPhaseIndex >= 0 &&
                 lastExecutedDescriptorIndex === -1) {
            const lastExecuted = test.phases[lastExecutedPhaseIndex];
            for (const descriptor of descriptors) {
              if (descriptor.descriptorId === lastExecuted.descriptorId) {
                lastExecutedDescriptorIndex = descriptors.indexOf(descriptor);
                // Don't break here, in case the same phase ran multiple times.
              }
            }
            lastExecutedPhaseIndex--;
          }

          // If we do not recognize the descriptor ID of the executing phase,
          // it should be the test start phase, and we can continue as normal.
          // If it isn't, then fail in a non-horrible way.
          if (lastExecutedDescriptorIndex === -1 && numExecutedPhases > 1) {
            console.error(
                'Unrecognized phase descriptor ID.', test.phases, descriptors);
            return test;
          }

          // Insert the phase descriptors between the last executed phase and
          // any teardown phases.
          test.phases.splice(
              lastExecutedPhaseIndex + 2, 0,
              ...descriptors.slice(lastExecutedDescriptorIndex + 1));
          return test;
        })
        // Degrade gracefully if we can't get the phase descriptors.
        .catch(() => {
          return Observable.of(test);
        });
  }

  private getOrRequestPhaseDescriptors(test: TestState) {
    if (!(test.testId in this.phaseDescriptorPromise)) {
      const testBaseUrl = getTestBaseUrl(this.config.dashboardEnabled, test);
      const url = `${testBaseUrl}/phases`;
      this.phaseDescriptorPromise[test.testId] =
          this.http.get(url)
              .toPromise()
              .then((response: Response) => {
                const rawDescriptors = response.json().data;
                const descriptors = rawDescriptors.map(makePhaseFromDescriptor);
                return descriptors;
              })
              .catch(error => {
                const tooltip = messageFromErrorResponse(error);
                this.flashMessage.error(
                    'HTTP request for phase descriptors failed.', tooltip);
                return Promise.reject(error);
              });
    }
    return Observable.fromPromise(this.phaseDescriptorPromise[test.testId]);
  }

  /**
   * Step 4: Update our data store with new test information.
   */
  private applyResponse(test: TestState, station: Station) {
    // If we have old information for this test, update it.
    if (test.testId in this.testsById) {
      const oldTest = this.testsById[test.testId];
      // Alert the operator when the test exits early.
      if (oldTest.status !== test.status) {
        if (test.status === TestStatus.error) {
          this.flashMessage.error(
              'The test exited early due to an error. View the test logs for ' +
              'details.');
        } else if (test.status === TestStatus.timeout) {
          this.flashMessage.warn('The test exited early due to timeout.');
        } else if (test.status === TestStatus.aborted) {
          this.flashMessage.warn('The test was aborted.');
        }
      }
      Object.assign(oldTest, test);
    }

    // Otherwise, add the new test.
    else {
      this.testsById[test.testId] = test;
      this.testsByStation[station.hostPort] = test;
    }
  }
}
