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
 * @fileoverview A directive for a starred stations footer.
 */

/**
 * @const {string} An event to notify when the list of starred stations
 * displayed changes.
 */
var STARLIST_CHANGED_EVENT = 'starlist-changed';
module.exports.STARLIST_CHANGED_EVENT = STARLIST_CHANGED_EVENT;

function StarredStations() {
  return {
    restrict: 'A',
    templateUrl: 'starredstations.html',
    controller: StarredController,
    controllerAs: 'Controller',
    link: function($scope) {
      // linking occurs after render so we can emit an event here
      $scope.$broadcast(STARLIST_CHANGED_EVENT, {});
    },
  };
}
module.exports.StarredStations = StarredStations;

function StarredController($scope, starService, stationsService, $timeout) {
  this.$scope = $scope;
  this.starService = starService;
  this.stationsService = stationsService;

  this.stations = [];
  $scope.$watch('Controller.getStarredStations_()', function(newVal) {
    this.stations = newVal;
    $timeout(function() { $scope.$broadcast(STARLIST_CHANGED_EVENT, {}); }, 0);
  }.bind(this), true);
}

StarredController.prototype.hasStarredStations = function() {
  return this.starService.getStarred().length > 0;
};

StarredController.prototype.getStarredStations_ = function() {
  var starred = this.starService.getStarred();
  // TODO: Move to station specific service instead of
  // the listing service.
  return this.stationsService.getStations().filter(function(station) {
    return starred.indexOf(station.stationName) != -1;
  });
};
