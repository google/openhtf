/**
 * @fileoverview A simple directive which sets the parameter status.
 */

var angular = require('angular');
var proto = require('openxtf-proto').openxtf;

function ParamValueDirective() {
  return {
    template: '<span>{{C.getValue()}}</span>',
    scope: {'parameter': '&oxParamValue'},
    controller: ParamValueController,
    controllerAs: 'C',
  };
}
module.exports = ParamValueDirective;

/**
 * @constructor
 * @param {angular.Scope} $scope
 */
function ParamValueController($scope) {
  this.$scope = $scope;
}

/** @return {string|number} */
ParamValueController.prototype.getValue = function() {
  var p = this.$scope.parameter();
  if (angular.isNumber(p.numeric_value)) {
    // can't easily do units since our proto parser doesn't support it
    // we'd have to either parse them in python and serve them separately
    // or fix protobuf.js
    return p.numeric_value;
  } else if (angular.isString(p.text_value)) {
    return p.text_value;
  }
  return "";
};
