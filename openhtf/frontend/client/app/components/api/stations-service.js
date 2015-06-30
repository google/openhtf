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
