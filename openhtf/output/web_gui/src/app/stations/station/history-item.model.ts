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
 * Summary information about a test run available in the history.
 */

import { TestState } from '../../shared/models/test-state.model';

export enum HistoryItemStatus {
  unloaded,
  loading,
  loaded,
  error,
}

export interface HistoryItemParams {
  dutId: string|null;
  fileName: string|null;
  drawAttention: boolean;
  startTimeMillis: number|null;
  status: HistoryItemStatus;
  testState: TestState|null;
}

export class HistoryItem {
  dutId: string|null;
  fileName: string|null;
  drawAttention: boolean;  // Whether to draw attention to a new history item.
  startTimeMillis: number|null;
  status: HistoryItemStatus;
  testState: TestState|null;  // Null if status is not `loaded`.

  constructor(params: HistoryItemParams) {
    Object.assign(this, params);
  }

  // Get an ID that we can trust to be unique for all history items from a
  // given station.
  get uniqueId(): string {
    if (this.dutId === null && this.startTimeMillis === null) {
      if (this.fileName === null) {
        throw new Error(
            'History item must have file name, or DUT ID and start time.');
      }
      return this.fileName;
    }
    return `${this.dutId}\$${this.startTimeMillis}`;
  }
}
