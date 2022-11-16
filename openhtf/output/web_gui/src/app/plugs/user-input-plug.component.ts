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

import {trigger} from '@angular/animations';
import {Component, ElementRef} from '@angular/core';
import {Http} from '@angular/http';

import {ConfigService} from '../core/config.service';
import {FlashMessageService} from '../core/flash-message.service';
import {washIn} from '../shared/animations';

import {BasePlug} from './base-plug';

const PLUG_NAME = 'openhtf.plugs.user_input.UserInput';

/**
 * @param default: the default prompt string for element.
 * @param error: the error message for element.
 * @param id: the identifier for the element.
 * @param message: the message to display to the operator.
 * @param text-input: the text input provided by the operator.
 * @param image-url: url to embedded image in the element.
 */
export declare interface UserInputPlugState {
  default?: string;  // Used by ui_plugs.advanced_user_input.AdvancedUserInput.
  error?: string;    // Used by ui_plugs.advanced_user_input.AdvancedUserInput.
  id: string;
  message: string;
  'text-input': string;
  'image-url': string;
  'is-user-question': string;
  'button-1-text': string;
  'button-2-text': string;
  'button-3-text': string;
}

/**
 * @param lastPromptId: identifier of last prompt.
 * @param lastPromptHtml: html contents of last prompt.
 */
@Component({
  animations: [trigger('animateIn', washIn)],
  selector: 'htf-user-input-plug',
  templateUrl: './user-input-plug.component.html',
  styleUrls: ['./user-input-plug.component.scss'],
})
export class UserInputPlugComponent extends BasePlug {
  private lastPromptId: string;
  private lastPromptHtml: string;

  constructor(
      config: ConfigService, http: Http, flashMessage: FlashMessageService,
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

  is_user_question() {
  	return (((this.getPlugState()['button-1-text'] !== null) && (this.getPlugState()['button-1-text'].length !== 0))
  		 ||((this.getPlugState()['button-2-text'] !== null) && (this.getPlugState()['button-2-text'].length !== 0))
  		 ||((this.getPlugState()['button-3-text'] !== null) && (this.getPlugState()['button-3-text'].length !== 0))
  	);
  }


 Button_1() {
    return this.getPlugState()['button-1-text'];
 }

  Button_2() {
    return this.getPlugState()['button-2-text'];
  }

  Button_3() {
    return this.getPlugState()['button-3-text'];
  }


  sendAnswer(input: string) {
    const promptId = this.getPlugState().id;
    let response: string;
    if (this.is_user_question()) {
      response = input.trim();
    } else {
      response = '';
    }
    this.respond('respond', [promptId, response]);
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
