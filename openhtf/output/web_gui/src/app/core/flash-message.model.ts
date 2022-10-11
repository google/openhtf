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
 * A message flashed on the screen for a set amount of time.
 */

let messageCount = 0;  // Used to create unique message IDs.

export enum FlashMessageType {
  error,
  warn,
}

export class FlashMessage {
  hasTooltip: boolean;
  id: number;
  isDismissed: boolean;  // Message should begin exit animation.
  showTooltip: boolean;

  constructor(
      public content: string, public tooltip: string|null,
      public type: FlashMessageType) {
    this.id = messageCount++;
    this.isDismissed = false;
    this.hasTooltip = Boolean(tooltip);
    this.showTooltip = false;
  }
}
