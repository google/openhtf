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
 * Makes requests for past test run history.
 */

import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';

import { ConfigService } from '../../core/config.service';
import { FlashMessageService } from '../../core/flash-message.service';
import { Station } from '../../shared/models/station.model';
import { TestState } from '../../shared/models/test-state.model';
import { getStationBaseUrl, messageFromHttpClientErrorResponse, sortByProperty } from '../../shared/util';

import { HistoryItem, HistoryItemStatus } from './history-item.model';
import { RawTestState, makeTest } from './station-data';

export interface TestStateCache { [historyItemId: string]: TestState; }

interface RawHistoryItemList {
  data: RawHistoryItem[];
}

interface RawHistoryItem {
  dut_id: string;
  file_name: string;
  start_time_millis: number;
}

@Injectable()
export class HistoryService {
  private readonly cache: {[stationHostPort: string]: TestStateCache} = {};
  private readonly history: {[stationHostPort: string]: HistoryItem[]} = {};

  constructor(
      private config: ConfigService, private http: HttpClient,
      private flashMessage: FlashMessageService) {}

  getCache(station: Station) {
    if (!(station.hostPort in this.cache)) {
      this.cache[station.hostPort] = {};
    }
    return this.cache[station.hostPort];
  }

  getHistory(station: Station) {
    if (!(station.hostPort in this.history)) {
      this.history[station.hostPort] = [];
    }
    return this.history[station.hostPort];
  }

  loadItem(station: Station, historyItem: HistoryItem): Promise<TestState> {
    if (historyItem.status === HistoryItemStatus.loading ||
        historyItem.status === HistoryItemStatus.loaded) {
      throw new Error(
          'Cannot load a history item that is loading or has loaded.');
    }

    const baseUrl = getStationBaseUrl(this.config.dashboardEnabled, station);
    const url = `${baseUrl}/history/${historyItem.fileName}`;
    historyItem.status = HistoryItemStatus.loading;

    return this.http.get<RawTestState>(url)
        .toPromise()
        .then(rawTestState => {
          const fileName = historyItem.fileName;
          const testState = makeTest(rawTestState, null, fileName, station);
          this.getCache(station)[historyItem.uniqueId] = testState;
          historyItem.status = HistoryItemStatus.loaded;
          historyItem.testState = testState;
          return testState;
        })
        .catch(error => {
          historyItem.status = HistoryItemStatus.error;
          return Promise.reject(error);
        });
  }

  // We prepend new items under the assumption that the startTimeMillis of the
  // new item is greater than every item in the history.
  prependItemFromTestState(station: Station, testState: TestState) {
    const historyItem = new HistoryItem({
      drawAttention: true,
      dutId: testState.dutId,
      fileName: null,
      startTimeMillis: testState.startTimeMillis,
      status: HistoryItemStatus.loaded,
      testState,
    });
    this.getCache(station)[historyItem.uniqueId] = testState;
    // Note: In your typical Javascript implementation this will take O(n) time.
    // It seems this may start to be an issue if we have ~50,000 history items.
    this.getHistory(station).unshift(historyItem);
  }

  refreshList(station: Station): Promise<undefined> {
    const baseUrl = getStationBaseUrl(this.config.dashboardEnabled, station);
    const url = `${baseUrl}/history`;

    return this.http.get<RawHistoryItemList>(url)
               .toPromise()
               .then(response => {
                 const rawHistoryItems = response.data;
                 this.getHistory(station).length = 0;
                 const stationHistory = rawHistoryItems.map(rawItem => {
                   const historyItem = new HistoryItem({
                     drawAttention: false,
                     dutId: rawItem.dut_id,
                     fileName: rawItem.file_name,
                     startTimeMillis: rawItem.start_time_millis,
                     status: HistoryItemStatus.unloaded,
                     testState: null,
                   });
                   if (historyItem.uniqueId in this.getCache(station)) {
                     const testState =
                         this.getCache(station)[historyItem.uniqueId];
                     historyItem.status = HistoryItemStatus.loaded,
                     historyItem.testState = testState;
                   }
                   return historyItem;
                 });
                 sortByProperty(stationHistory, 'startTimeMillis', true);
                 this.history[station.hostPort].push(...stationHistory);
               })
               .catch((error: HttpErrorResponse) => {
                 if (error.status === 404) {
                   console.info('History from disk appears to be disabled.');
                 } else {
                   const tooltip = messageFromHttpClientErrorResponse(error);
                   this.flashMessage.error(
                       'HTTP request for history failed.', tooltip);
                 }
                 return Promise.reject(error);
               }) as any;
  }

  // The filename of a history item is unknown if the history item was created
  // from via prependItemFromTestState. To open attachments on that test, the
  // filename must be retrieved after the test record is written to disk.
  retrieveFileName(station: Station, historyItem: HistoryItem) {
    if (historyItem.status !== HistoryItemStatus.loaded) {
      throw new Error(
          'Cannot retrieve file name for a history item that is not loaded.');
    }

    const baseUrl = getStationBaseUrl(this.config.dashboardEnabled, station);
    const url =
        (`${baseUrl}/history?dutId=${historyItem.dutId}` +
         `&startTimeMillis=${historyItem.startTimeMillis}`);

    return this.http.get<RawHistoryItemList>(url).toPromise().then(response => {
      const rawHistoryItems = response.data;
      if (rawHistoryItems.length === 0) {
        return Promise.reject(new Error('Server returned no history items.'));
      } else if (rawHistoryItems.length > 1) {
        return Promise.reject(
            new Error('Server returned more than one history item.'));
      }
      const rawHistoryItem = rawHistoryItems[0];

      historyItem.fileName = rawHistoryItem.file_name;
      historyItem.testState.fileName = rawHistoryItem.file_name;
    });
  }
}
