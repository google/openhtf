// Copyright 2014 Google Inc. All Rights Reserved.
// 
//  Licensed under the Apache License, Version 2.0 (the "License");
//  you may not use this file except in compliance with the License.
//  You may obtain a copy of the License at
// 
//      http://www.apache.org/licenses/LICENSE-2.0
// 
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.


/**
 * @fileoverview Stations service.
 */

/** @enum {string} */
var StationState = module.exports.StationState = {
  RUNNING: 'Running',
  OFFLINE: 'Offline',
  UNKNOWN: 'Unknown'
};

/** @constructor */
function StationsService($http, $log) {
  this.$http = $http;
  this.$log = $log;

  this.outstandingFetch = null;
  this.stations = [];
}
module.exports.StationService = StationsService;

/**
 * Fetches the stations.
 * @return {Promise}
 */
StationsService.prototype.fetchStationsNow = function() {
  if (this.outstandingFetch) {
    return this.outstandingFetch;
  }

  this.outstandingFetch =
      this.$http.get('/api/stations')
          .then(this.handleFetchSuccess.bind(this))
          .finally(function() { this.outstandingFetch = null; }.bind(this));
  return this.outstandingFetch;
};

/** @return {boolean} True if currently fetching data. */
StationsService.prototype.isFetching = function() {
  return angular.isDefined(this.outstandingFetch);
};

/** @return {Array.<{{stationName: string, state: StationState}}} */
StationsService.prototype.getStations = function() {
  return this.stations.slice(0);
};

/**
 * Handles fetching successfully.
 * @return {Array.<{{stationName: string, state: StationState}}>}
 */
StationsService.prototype.handleFetchSuccess = function(response) {
  var data = response.data;
  // We expect a map of stationName to status
  this.stations = Object.keys(data).map(function(stationName) {
    var rawState = data[stationName];
    var state = StationState.UNKNOWN;
    if (!(rawState in StationState)) {
      this.$log.warn('Station status now recognized ' + stationName +
                     ' in weird state ' + rawState);
    } else {
      state = StationState[rawState];
    }
    return {stationName: stationName, state: state};
  }, this);

  this.stations.sort(function(stationOne, stationTwo) {
    if (stationOne.stationName < stationTwo.stationName) {
      return -1;
    } else if (stationOne.stationName > stationTwo.stationName) {
      return 1;
    }
    return 0;
  });
  this.$log.debug('Station list updated');
  return this.stations;
};
