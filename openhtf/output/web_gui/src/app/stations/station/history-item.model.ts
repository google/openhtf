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
