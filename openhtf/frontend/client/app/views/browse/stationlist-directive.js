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


