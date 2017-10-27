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
