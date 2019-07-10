/**
 * Widget displaying previous test runs on a station.
 */

import { trigger } from '@angular/animations';
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';

import { FlashMessageService } from '../../core/flash-message.service';
import { washAndExpandIn } from '../../shared/animations';
import { Station, StationStatus } from '../../shared/models/station.model';
import { TestState, TestStatus } from '../../shared/models/test-state.model';
import { messageFromErrorResponse } from '../../shared/util';

import { HistoryItem, HistoryItemStatus } from './history-item.model';
import { HistoryService } from './history.service';

// Emitted by the component when a test is selected or deselected.
export class TestSelectedEvent {
  constructor(public test: TestState) {}
}

const listItemHeight = 48;

@Component({
  animations: [trigger('animateIn', washAndExpandIn(listItemHeight))],
  selector: 'htf-history',
  templateUrl: './history.component.html',
  styleUrls: ['./history.component.scss'],
})
export class HistoryComponent implements OnChanges {
  @Input() selectedTest: TestState|null;
  @Input() station: Station;
  @Output() onSelectTest = new EventEmitter<TestSelectedEvent>();

  readonly collapsedNumTests = 5;
  HistoryItemStatus = HistoryItemStatus;
  TestStatus = TestStatus;
  expanded = false;
  hasError = false;
  history: HistoryItem[] = [];
  historyFromDiskEnabled = false;
  isLoading = false;

  private lastClickedItem: HistoryItem|null = null;

  constructor(
      private historyService: HistoryService,
      private flashMessage: FlashMessageService) {}

  ngOnChanges(changes: SimpleChanges) {
    if ('station' in changes) {
      if (this.station.status === StationStatus.online) {
        // TODO(kenadia): The current behavior is that this only triggers when
        // the station page first loads. To better handle edge cases, the
        // history list should be refreshed when a new connection to a station
        // is established, for example if the user clicks on the refresh station
        // button, or if a station that was offline comes online.
        // I think that we can best accomplish this by making station objects
        // immutable. This will be done as part of a future refactor.
        this.loadHistory();
        this.history = this.historyService.getHistory(this.station);
      }
    }
  }

  isSelected(historyItem: HistoryItem) {
    return (
        historyItem.status === HistoryItemStatus.loaded &&
        historyItem.testState === this.selectedTest);
  }

  onClick(historyItem: HistoryItem) {
    this.lastClickedItem = historyItem;

    if (historyItem.status === HistoryItemStatus.loading) {
      return;
    }

    // If the test state has been loaded already, select/deselect it.
    if (historyItem.status === HistoryItemStatus.loaded) {
      this.selectTest(historyItem.testState);

      if (historyItem.testState === this.selectedTest) {
        // The fileName will be null if the history item was created from a test
        // record/state retrieved by the StationService. We are unable to access
        // attachments until we know the file name, so try to retrieve it now.
        if (historyItem.testState.fileName === null) {
          this.historyService.retrieveFileName(this.station, historyItem)
              .catch(() => {
                if (this.historyFromDiskEnabled) {
                  this.flashMessage.warn(
                      'Could not retrieve history from disk, so attachments ' +
                      'are not available. You may try again later.');
                }
              });
        }
      }
      return;
    }

    this.historyService.loadItem(this.station, historyItem)
        .then((testState: TestState) => {
          if (this.lastClickedItem === historyItem) {
            this.selectTest(testState);
          }
        })
        .catch(error => {
          console.error(error.stack);
          const tooltip = messageFromErrorResponse(error);
          this.flashMessage.error('Error loading history item.', tooltip);
        });
  }

  toggleExpanded() {
    this.expanded = !this.expanded;
  }

  private loadHistory() {
    this.hasError = false;
    this.isLoading = true;
    this.historyFromDiskEnabled = false;

    this.historyService.refreshList(this.station)
        .then(() => {
          this.isLoading = false;
          this.historyFromDiskEnabled = true;
        })
        .catch(error => {
          this.isLoading = false;
          this.hasError = true;
          this.historyFromDiskEnabled = error.status !== 404;
        });
  }

  private selectTest(test: TestState) {
    if (test === this.selectedTest) {
      this.selectedTest = null;
    } else {
      this.selectedTest = test;
    }
    this.onSelectTest.emit(new TestSelectedEvent(this.selectedTest));
  }
}
