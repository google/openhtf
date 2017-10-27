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
