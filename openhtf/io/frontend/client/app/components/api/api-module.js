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
