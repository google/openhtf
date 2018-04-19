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
