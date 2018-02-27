/**
 * Provides methods for flashing messages at the top of the screen.
 *
 * One message is displayed at a time. If multiple messages are added in rapid
 * succession, they are queued and displayed in turn.
 */

import { Injectable } from '@angular/core';

import { FlashMessage, FlashMessageType } from './flash-message.model';

// Should match the CSS animation duration in vars.scss.
const dismissalDurationMs = 400;

const flashDurationMs = 5000;

@Injectable()
export class FlashMessageService {
  /**
   * A queue of messages. The first message in the list will be displayed.
   */
  messages: FlashMessage[] = [];

  private dismissalJob: NodeJS.Timer|number|null = null;

  /**
   * Cancels the countdown for dismissing the displayed message.
   *
   * Called by FlashMessagesComponent.
   */
  cancelDismissal() {
    if (this.dismissalJob !== null) {
      clearTimeout(this.dismissalJob as NodeJS.Timer);
      this.dismissalJob = null;
    }
  }

  /**
   * Dismisses the displayed message.
   *
   * Called by FlashMessagesComponent.
   */
  dismissEarly() {
    this.cancelDismissal();
    this.dismiss();
  }

  /**
   * Starts the countdown for dismissing the displayed message.
   *
   * Called by FlashMessagesComponent.
   */
  startDismissal() {
    if (this.messages[0].isDismissed) {
      return;
    }
    this.cancelDismissal();  // Reset timeout if it was set.
    this.dismissalJob = setTimeout(() => {
      this.dismiss();
      this.dismissalJob = null;
    }, flashDurationMs);
  }

  error(content: string, tooltip: string|null = null) {
    this.addMessage(new FlashMessage(content, tooltip, FlashMessageType.error));
  }

  warn(content: string, tooltip: string|null = null) {
    this.addMessage(new FlashMessage(content, tooltip, FlashMessageType.warn));
  }

  private addMessage(message: FlashMessage) {
    this.messages.push(message);
    if (this.messages.length === 1) {
      this.startDismissal();
    }
  }

  private dismiss() {
    this.messages[0].isDismissed = true;
    setTimeout(() => {
      this.messages.shift();
      if (this.messages.length > 0) {
        this.startDismissal();
      }
    }, dismissalDurationMs + 100);  // Add a 100ms buffer for animation.
  }
}
