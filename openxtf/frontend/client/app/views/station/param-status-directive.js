/**
 * @fileoverview A simple directive which sets the parameter status.
 */

var proto = require('openxtf-proto').openxtf;

function ParamStatusDirective() {
  return {
    template:
        '<span data-ng-class="C.getStatusClass()">{{C.getStatusText() | uppercase}}</span>',
    scope: {'status': '&oxParamStatus'},
    controller: ParamStatusController,
    controllerAs: 'C',
  };
}
module.exports = ParamStatusDirective;

function ParamStatusController($scope) {
  this.$scope = $scope;
}

/** @return {string} Param class pass/fail. */
ParamStatusController.prototype.getStatusClass = function() {
  switch (this.$scope.status()) {
    case proto.Status.PASS:
      return 'station-param-pass';
    case proto.Status.FAIL:
      return 'station-param-fail';
    default:
      return 'station-param-unset';
  }
};

/** @return {string} Text for the parameter status. */
ParamStatusController.prototype.getStatusText = function() {
  switch (this.$scope.status()) {
    case proto.Status.PASS:
      return 'pass';
    case proto.Status.FAIL:
      return 'fail';
    default:
      return 'not set';
  }
};
