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
 * @fileoverview A simple directive which sets the parameter status.
 */

var angular = require('angular');
var proto = require('openhtf-proto').openhtf;

function ParamLimitDirective() {
  return {
    template: '<span>{{C.getLimit()}}</span>',
    scope: {'parameter': '&oxParamLimit'},
    controller: ParamLimitController,
    controllerAs: 'C',
  };
}
module.exports = ParamLimitDirective;

/**
 * @constructor
 * @param {angular.Scope} $scope
 */
function ParamLimitController($scope) {
  this.$scope = $scope;
}

/** @return {string} */
ParamLimitController.prototype.getLimit = function() {
  var p = this.$scope.parameter();
  if (angular.isNumber(p.numeric_minimum) || angular.isNumber(p.numeric_maximum)) {
    return this.getNumericLimits(p.numeric_minimum, p.numeric_maximum);
  } else if (angular.isString(p.expected_text)) {
    return p.expected_text;
  }
  return "";
};

/**
 * @param {proto.TestParameter} param
 * @return {string}
 */
ParamLimitController.prototype.getNumericLimits = function(min, max) {
  if (angular.isNumber(min) && min === max) {
    return 'x == ' + min;
  }

  var v = 'x';
  if (angular.isNumber(min)) {
    v = min.toString() + ' <= ' + v;
  }
  if (angular.isNumber(max)) {
    v += ' <= ' + max.toString();
  }
  return v;
};
