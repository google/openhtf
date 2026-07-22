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

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, from } from 'rxjs';
import { map, catchError, mergeMap } from 'rxjs/operators';

import { ConfigService } from '../../core/config.service';
import { FlashMessageService } from '../../core/flash-message.service';
import { Phase } from '../../shared/models/phase.model';
import { Station } from '../../shared/models/station.model';
import { TestState, TestStatus } from '../../shared/models/test-state.model';
import { SockJsMessage, SockJsService } from '../../shared/sock-js.service';
import { Subscription } from '../../shared/subscription';
import { getStationBaseUrl, getTestBaseUrl, messageFromHttpClientErrorResponse } from '../../shared/util';

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
    private historyService: HistoryService, private http: HttpClient,
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
      this.messages.pipe(
            // Use mergeMap since this.applyPhaseDescriptors returns Observable.
        mergeMap((message: SockJsMessage) => {
              const response = StationService.validateResponse(message.data);
              console.debug('StationService received response:', response);
              const test = this.parseResponse(response, station);
              return this.applyPhaseDescriptors(test);
            })
      ).subscribe(test => {
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
   */
  private applyPhaseDescriptors(test: TestState): Observable<TestState> {
    const descriptorsPromise = this.getOrRequestPhaseDescriptors(test);
    return from(descriptorsPromise).pipe(
      map((descriptors: Phase[]) => {
          // Counts all phases that have started execution.
          const numExecutedPhases = test.phases.length;

          if (numExecutedPhases === 0) {
            test.phases.push(...descriptors);
            return test;
          }

          let lastExecutedPhaseIndex = numExecutedPhases - 1;
          let lastExecutedDescriptorIndex = -1;
          while (lastExecutedPhaseIndex >= 0 &&
                 lastExecutedDescriptorIndex === -1) {
            const lastExecuted = test.phases[lastExecutedPhaseIndex];
            for (const descriptor of descriptors) {
              if (descriptor.descriptorId === lastExecuted.descriptorId) {
                lastExecutedDescriptorIndex = descriptors.indexOf(descriptor);
              }
            }
            lastExecutedPhaseIndex--;
          }

          if (lastExecutedDescriptorIndex === -1 && numExecutedPhases > 1) {
            console.error(
                'Unrecognized phase descriptor ID.', test.phases, descriptors);
            return test;
          }

          test.phases.splice(
              lastExecutedPhaseIndex + 2, 0,
              ...descriptors.slice(lastExecutedDescriptorIndex + 1));
          return test;
      }),
        // Degrade gracefully if we can't get the phase descriptors.
      catchError(() => {
        return of(test);
      })
    );
  }

  private getOrRequestPhaseDescriptors(test: TestState) {
    if (!(test.testId in this.phaseDescriptorPromise)) {
      const testBaseUrl = getTestBaseUrl(this.config.dashboardEnabled, test);
      const url = `${testBaseUrl}/phases`;
      this.phaseDescriptorPromise[test.testId] =
        this.http.get<{ data: any[] }>(url)
              .toPromise()
        .then((response) => {
          const rawDescriptors = response.data;
                const descriptors = rawDescriptors.map(makePhaseFromDescriptor);
                return descriptors;
              })
              .catch(error => {
                const tooltip = messageFromHttpClientErrorResponse(error);
                this.flashMessage.error(
                    'HTTP request for phase descriptors failed.', tooltip);
                return Promise.reject(error);
              });
    }
    return this.phaseDescriptorPromise[test.testId];
  }

  /**
   * Step 4: Update our data store with new test information.
   */
  private applyResponse(test: TestState, station: Station) {
    if (test.testId in this.testsById) {
      const oldTest = this.testsById[test.testId];
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
    else {
      this.testsById[test.testId] = test;
      this.testsByStation[station.hostPort] = test;
    }
  }
}
