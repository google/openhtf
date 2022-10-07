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
 * Root component of the app.
 */

import { Component, ElementRef } from '@angular/core';

import { ConfigService } from './core/config.service';
import { Station } from './shared/models/station.model';

import '../style/main.scss';

@Component({
  selector: 'htf-app',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent {
  selectedStation: Station|null = null;

  constructor(configService: ConfigService, ref: ElementRef) {
    // We can't access the config as an Angular input property because it is on
    // the root element, so access it as an attribute instead.
    const configString = ref.nativeElement.getAttribute('config');

    let config: {};
    try {
      config = JSON.parse(configString);
    } catch (e) {
      // This is expected to occur when running off of the devserver.
      console.debug('Could not parse config, falling back to defaults.');
      configService.initialize({});
      return;
    }

    configService.initialize(config);
  }
}
