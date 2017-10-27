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
