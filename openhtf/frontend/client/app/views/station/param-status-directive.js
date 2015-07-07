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

var proto = require('openhtf-proto').openhtf;

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
