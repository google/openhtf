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
 * Component representing the UserInput plug.
 */

import { trigger } from '@angular/animations';
import { Component, ElementRef, Input, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient } from '@angular/common/http';

import {ConfigService} from '../core/config.service';
import {FlashMessageService} from '../core/flash-message.service';
import {washIn} from '../shared/animations';
import { TestState } from '../shared/models/test-state.model';

import {BasePlug} from './base-plug';

const PLUG_NAME = 'openhtf.plugs.user_input.UserInput';

/**
 * @param default: the default prompt string for element.
 * @param error: the error message for element.
 * @param id: the identifier for the element.
 * @param message: the message to display to the operator.
 * @param text-input: the text input provided by the operator.
 * @param image-url: url to embedded image in the element.
 * @param buttons: buttons to show in place of the default one, if any.
 */
export declare interface UserInputPlugState {
  default?: string;  // Used by ui_plugs.advanced_user_input.AdvancedUserInput.
  error?: string;    // Used by ui_plugs.advanced_user_input.AdvancedUserInput.
  id: string;
  message: string;
  'text-input': string;
  'image-url': string;
  buttons?: UserInputButton[];
}

/**
 * @param text: the button label.
 * @param value: the response sent when the button is pressed.
 * @param color: 'blue', 'red' or 'grey' for a built-in style, or a CSS color.
 * @param text-color: CSS color for the label, or null for the default.
 */
export declare interface UserInputButton {
  text: string;
  value: string;
  color: string;
  'text-color': string|null;
}

const BUILT_IN_BUTTON_COLORS = ['blue', 'red', 'grey'];

/**
 * @param lastPromptId: identifier of last prompt.
 * @param lastPromptHtml: html contents of last prompt.
 */
@Component({
    animations: [trigger('animateIn', washIn)],
    selector: 'htf-user-input-plug',
    templateUrl: './user-input-plug.component.html',
    styleUrls: ['./user-input-plug.component.scss'],
    changeDetection: ChangeDetectionStrategy.Eager,
    standalone: false
})
export class UserInputPlugComponent extends BasePlug {
  @Input() override test: TestState;
  private lastPromptId: string;
  private lastPromptHtml: string;

  constructor(
    config: ConfigService, http: HttpClient, flashMessage: FlashMessageService,
      private ref: ElementRef) {
    super(PLUG_NAME, config, http, flashMessage);
  }


  get error() {
    return this.getPlugState().error;
  }

  get prompt() {
    const state = this.getPlugState();
    // Run this when a new prompt is set.
    if (this.lastPromptId !== state.id) {
      this.lastPromptId = state.id;
      const convertedHtml =
          state.message.replace(/&#10;/g, '<br>');  // Convert newlines.
      this.lastPromptHtml = convertedHtml;
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

  hasImage() {
    return this.getPlugState()['image-url'];
  }

  get Image_URL() {
    return this.getPlugState()['image-url'];
  }

  get buttons(): UserInputButton[] {
    return this.getPlugState().buttons || [];
  }

  buttonClass(button: UserInputButton) {
    const color =
        BUILT_IN_BUTTON_COLORS.includes(button.color) ? button.color : 'grey';
    return `htf-rounded-button-${color}`;
  }

  buttonStyle(button: UserInputButton) {
    if (BUILT_IN_BUTTON_COLORS.includes(button.color)) {
      return {'color': button['text-color']};
    }
    return {
      'background-color': button.color,
      'border-color': button.color,
      'color': button['text-color'] || 'white',
    };
  }

  sendButtonResponse(input: HTMLInputElement, button: UserInputButton) {
    this.respond('respond', [
      this.getPlugState().id, this.takeTextResponse(input), button.value,
    ]);
  }

  onEnter(input: HTMLInputElement) {
    // With buttons, the operator still has to pick one.
    if (this.buttons.length === 0) {
      this.sendResponse(input);
    }
  }

  sendResponse(input: HTMLInputElement) {
    this.respond(
        'respond', [this.getPlugState().id, this.takeTextResponse(input)]);
  }

  private takeTextResponse(input: HTMLInputElement) {
    if (!this.hasTextInput()) {
      return '';
    }
    const response = input.value;
    input.value = '';
    return response;
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
