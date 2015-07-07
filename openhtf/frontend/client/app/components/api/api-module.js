/**
 * @fileoverview The module for our api services.
 */

var angular = require('angular');
var stations = require('./stations-service.js');
var poller = require('./poller-factory.js');
var StationDataService = require('./stationdata-service.js');

var m = module.exports = angular.module('openhtf.components.api', []);
m.service('stationsService', stations.StationService);
m.service('pollerFactory', poller.PollFactory);
m.service('stationDataService', StationDataService);

/** A poller which can poll for stations services. */
m.factory('stationsServicePoller', function(pollerFactory, stationsService) {
  return pollerFactory.create(
      stationsService.fetchStationsNow.bind(stationsService), 'Station Poller');
});

/** Instantiates our pollers so they start doing exciting things. */
m.run(function(stationsServicePoller) {
  stationsServicePoller.schedulePoll();
});
