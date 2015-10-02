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
 * @fileoverview A directive for listing stations.
 */

var angular = require('angular');
var template = require('./browse.stationlist.html');

var m = module.exports = angular.module('openhtf.views.browse.stationlist', [
    template.name]);

m.directive('oxStationList', function() {
  return {
    restrict: 'A',
    scope: true,
    templateUrl: 'browse.stationlist.html',
    controller: StationListController,
    controllerAs: 'Controller'
  };
});

/**
 * @param {angular.Scope} $scope
 * @constructor
 */
function StationListController($scope, stationsService, starService) {
  this.$scope = $scope;
  this.stationsService = stationsService;
  this.starService = starService;
}

/** @return {Array.<{{stationName: string, state: StationState}}>} */
StationListController.prototype.getStations = function() {
  var stations = this.stationsService.getStations();
  stations.sort(function(one, two) {
    // we not these so that we can sort stars to the front
    var notStarOne = !this.starService.isStarred(one.stationName);
    var notStarTwo = !this.starService.isStarred(two.stationName);
    var compareOne = [notStarOne, one.stationName];
    var compareTwo = [notStarTwo, two.stationName];

    if (compareOne < compareTwo) {
      return -1;
    } else if (compareOne > compareTwo) {
      return 1;
    }
    return 0;
  }.bind(this));
  return stations;
};

/**
 * @param {string} stationName The station name.
 * @return {boolean} True if the station is starred.
 */
StationListController.prototype.isStarred = function(stationName) {
  return this.starService.isStarred(stationName);
};

/** @param {string} stationName */
StationListController.prototype.toggleStarred = function(stationName) {
  return this.starService.toggleStarred(stationName);
};


