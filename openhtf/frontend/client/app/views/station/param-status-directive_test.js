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
 * Tests for the param status directive.
 */

var directive = require('./param-status-directive.js');
var proto = require('openhtf-proto').openhtf;

describe('ParamStatusDirective', function() {
  function makeScope() {
    return {
      realstatus: proto.Status.PASS,
      status: function() { return this.realstatus; }
    };
  }
  var Controller = directive().controller;

  it('returns the status text', function() {
    var $scope = makeScope();
    var c = new Controller($scope);
    expect(c.getStatusText()).toEqual('pass');
    $scope.realstatus = proto.Status.TIMEOUT;
    expect(c.getStatusText()).toEqual('not set');
  });

  it('returns the status class if unset', function() {
    var $scope = makeScope();
    var c = new Controller($scope);
    expect(c.getStatusClass()).toEqual('station-param-pass');
    $scope.realstatus = proto.Status.TIMEOUT;
    expect(c.getStatusClass()).toEqual('station-param-unset');
  });
});
