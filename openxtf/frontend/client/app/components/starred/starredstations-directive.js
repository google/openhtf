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
  // TODO(alusco): Move to station specific service instead of
  // the listing service.
  return this.stationsService.getStations().filter(function(station) {
    return starred.indexOf(station.stationName) != -1;
  });
};
