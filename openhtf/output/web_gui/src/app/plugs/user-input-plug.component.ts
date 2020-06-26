/**
 * Component representing the UserInput plug.
 */

import { trigger } from '@angular/animations';

import { Component, ElementRef, SecurityContext } from '@angular/core';
import { Http } from '@angular/http';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

import { ConfigService } from '../core/config.service';
import { FlashMessageService } from '../core/flash-message.service';
import { washIn } from '../shared/animations';

import { BasePlug } from './base-plug';

const plugName = 'openhtf.plugs.user_input.UserInput';

export declare interface UserInputPlugState {
  default?: string;  // Used by ui_plugs.advanced_user_input.AdvancedUserInput.
  error?: string;    // Used by ui_plugs.advanced_user_input.AdvancedUserInput.
  id: string;
  message: string;
  'text-input': string;
}

@Component({
  animations: [trigger('animateIn', washIn)],
  selector: 'htf-user-input-plug',
  templateUrl: './user-input-plug.component.html',
  styleUrls: ['./user-input-plug.component.scss'],
})
export class UserInputPlugComponent extends BasePlug {
  private lastPromptId: string;
  private lastPromptHtml: SafeHtml;

  constructor(
      config: ConfigService, http: Http, flashMessage: FlashMessageService,
      private ref: ElementRef, private sanitizer: DomSanitizer) {
    super(plugName, config, http, flashMessage);
  }

  get error() {
    return this.getPlugState().error;
  }

  get prompt() {
    const state = this.getPlugState();
    // Run this when a new prompt is set.
    if (this.lastPromptId !== state.id) {
      this.lastPromptId = state.id;
      const safeHtml =
          this.sanitizer.sanitize(SecurityContext.HTML, state.message)
              .replace(/&#10;/g, '<br>');  // Convert newlines.
      this.lastPromptHtml = this.sanitizer.bypassSecurityTrustHtml(safeHtml);
      this.focusSelf();
      if (state.default) {
        this.setResponse(state.default);
      }
    }
    return this.lastPromptHtml;
  }

  hasTextInput() {
    return this.getPlugState()['text-input'];
  }

  sendResponse(input: HTMLInputElement) {
    const promptId = this.getPlugState().id;
    let response: string;
    if (this.hasTextInput()) {
      response = input.value;
      input.value = '';
    } else {
      response = '';
    }
    this.respond('respond', [promptId, response]);
  }

  protected getPlugState() {
    return super.getPlugState() as UserInputPlugState;
  }

  private focusSelf() {
    const input = this.ref.nativeElement.querySelector('input');
    if (input) {
      input.focus();
    }
  }

  private setResponse(response) {
    const input = this.ref.nativeElement.querySelector('input');
    if (input) {
      input.value = response;
    }
  }
}
