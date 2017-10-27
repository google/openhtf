/**
 * Component displaying messages created by the FlashMessageService.
 */

import { Component, Pipe, PipeTransform } from '@angular/core';

import { FlashMessage, FlashMessageType } from './flash-message.model';
import { FlashMessageService } from './flash-message.service';

// We use the ng- prefix to indicate CSS classes that are added dynamically.
const typeToCssClass = {
  [FlashMessageType.error]: 'ng-flash-message-error',
  [FlashMessageType.warn]: 'ng-flash-message-warn',
};

@Pipe({name: 'flashMessageTypeToClass'})
export class FlashMessageTypeToClass implements PipeTransform {
  transform(type: FlashMessageType): string {
    return typeToCssClass[type];
  }
}

@Component({
  selector: 'htf-flash-messages',
  templateUrl: './flash-messages.component.html',
  styleUrls: ['./flash-messages.component.scss'],
})
export class FlashMessagesComponent {
  constructor(private flashMessage: FlashMessageService) {}

  get message() {
    if (this.flashMessage.messages.length > 0) {
      return this.flashMessage.messages[0];
    }
  }

  dismiss() {
    this.flashMessage.dismissEarly();
  }

  onMouseEnter(message: FlashMessage) {
    this.flashMessage.cancelDismissal();
    message.showTooltip = message.hasTooltip;
  }

  onMouseExit(message: FlashMessage) {
    this.flashMessage.startDismissal();
    message.showTooltip = false;
  }
}
