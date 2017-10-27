/**
 * Summary info about a station.
 */

export enum StationStatus {
  online = 7,
  unreachable,
}

export class Station {
  cell: string|null;
  host: string;
  hostPort: string;  // Used to uniquely identify stations.
  label: string;
  port: string;
  stationId: string;
  status: StationStatus;
  testDescription: string|null;
  testName: string|null;

  // Using the class as the interface for its own constructor allows us to call
  // the constructor in named-argument style.
  constructor(params: Station) {
    Object.assign(this, params);
  }
}
