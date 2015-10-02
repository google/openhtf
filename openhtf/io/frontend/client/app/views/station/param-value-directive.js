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
