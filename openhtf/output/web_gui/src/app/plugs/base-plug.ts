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
 * Base class for plug components.
 */

import { Input } from '@angular/core';
import { Headers, Http, RequestOptions, Response } from '@angular/http';

import { ConfigService } from '../core/config.service';
import { FlashMessageService } from '../core/flash-message.service';
import { TestState } from '../shared/models/test-state.model';
import { messageFromErrorResponse } from '../shared/util';
import { getTestBaseUrl } from '../shared/util';

export abstract class BasePlug {
  @Input() test: TestState;

  // The plug name is a class name, or, if the plug is a subclass of another
  // plug, a comma-separated list of class names.
  //
  // For example:
  //     `openhtf.plugs.user_input.UserInput`
  // Or:
  //     `openhtf.plugs.user_input.UserInput,\
  //         openhtf.plugs.user_input.AdvancedUserInput`
  private plugName: string;

  constructor(
      private className: string, protected config: ConfigService,
      protected http: Http, protected flashMessage: FlashMessageService) {}

  plugExists(): boolean {
    return Boolean(this.test && this.getPlugState());
  }

  protected respond(method: string, args: Array<{}>) {
    const headers = new Headers({'Content-Type': 'application/json'});
    const options = new RequestOptions({headers});
    const testBaseUrl = getTestBaseUrl(this.config.dashboardEnabled, this.test);
    const plugUrl = `${testBaseUrl}/plugs/${this.plugName}`;
    const payload = JSON.stringify({method, args});

    this.http.post(plugUrl, payload, options)
        .subscribe(() => {}, (error: Response) => {
          const tooltip = messageFromErrorResponse(error);
          this.flashMessage.error(
              `An error occurred trying to respond to ` +
                  `plug ${this.plugName}.`,
              tooltip);
        });
  }

  protected getPlugState() {
    // If we previously found an active matching plug, use that plug as long
    // as it remains active (as long as the plug state is not null).
    if (this.plugName && this.test.plugStates[this.plugName]) {
      return this.test.plugStates[this.plugName];
    }

    // Find the first *active* plug (state is not null) whose MRO includes
    // this.className.
    for (const plugName of Object.keys(this.test.plugStates)) {
      if (this.test.plugStates[plugName] &&
          this.test.plugDescriptors[plugName].mro.indexOf(this.className) !==
              -1) {
        this.plugName = plugName;
        return this.test.plugStates[plugName];
      }
    }
  }
}
