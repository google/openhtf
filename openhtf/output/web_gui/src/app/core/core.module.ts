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
 * Contains classes used exactly once application-wide, used by the root module.
 *
 * See https://angular.io/docs/ts/latest/guide/ngmodule.html for more info
 * about modules in Angular.
 */

import { CommonModule } from '@angular/common';
import { NgModule, Optional, SkipSelf } from '@angular/core';

import { ConfigService } from './config.service';
import { FlashMessageService } from './flash-message.service';
import { FlashMessagesComponent, FlashMessageTypeToClass } from './flash-messages.component';

@NgModule({
  imports: [
    CommonModule,
  ],
  declarations: [
    FlashMessagesComponent,
    FlashMessageTypeToClass,
  ],
  providers: [
    ConfigService,
    FlashMessageService,
  ],
  exports: [CommonModule, FlashMessagesComponent],
})
export class CoreModule {
  // Prevent re-import of the CoreModule.
  // From:
  // https://angular.io/docs/ts/latest/guide/ngmodule.html#prevent-reimport
  constructor(@Optional() @SkipSelf() parentModule: CoreModule) {
    if (parentModule) {
      throw new Error(
          'CoreModule is already loaded. Import it in the AppModule only');
    }
  }
}
