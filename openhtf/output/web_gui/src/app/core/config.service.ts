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
 * Service for the global app configuration.
 */

import { Injectable } from '@angular/core';

type dashboard = 'dashboard';
type station = 'station';
const DASHBOARD_SERVER_TYPE: dashboard = 'dashboard';

interface Config {
  server_type?: dashboard|station;
  history_from_disk_enabled?: boolean;
}

// We will usually fall back to the default config during development.
const defaultConfig: Config = {
  server_type: DASHBOARD_SERVER_TYPE,
  history_from_disk_enabled: false,
};

@Injectable()
export class ConfigService {
  private config: Config = defaultConfig;

  // tslint:disable-next-line:no-any config is parsed from JSON, then validated
  initialize(config: any) {
    const extraKeys = Object.keys(config).filter(k => !(k in defaultConfig));

    if (extraKeys.length > 0) {
      console.warn('Received unknown config keys', extraKeys);
      for (const key of extraKeys) {
        delete config[key];
      }
    }

    this.config = {};
    Object.assign(this.config, defaultConfig);
    Object.assign(this.config, config);
  }

  get dashboardEnabled(): boolean {
    if (this.config === null) {
      throw new Error('Attempted to access config before it was initialized.');
    }
    return this.config.server_type === DASHBOARD_SERVER_TYPE;
  }
}
