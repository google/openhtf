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
 * Tests for the param value directive.
 */

var directive = require('./param-limit-directive.js');
var proto = require('openhtf-proto').openhtf;

describe('ParamLimitDirective', function() {
  function makeScope() {
    var p = new proto.TestParameter();
    return {
      parameter: function() { return this.p; },
      p: p
    };
  }
  var Controller = directive().controller;

  it('returns numeric = if values are same', function() {
    var $scope = makeScope();
    $scope.p.numeric_minimum = $scope.p.numeric_maximum = 5;
    var c = new Controller($scope);
    expect(c.getLimit()).toEqual('x == 5');
  });

  it('returns text limit', function() {
    var $scope = makeScope();
    $scope.p.expected_text = 'hi';
    var c = new Controller($scope);
    expect(c.getLimit()).toEqual('hi');
  });

  it('returns joined limit if both numeric limits are set', function() {
    var $scope = makeScope();
    $scope.p.numeric_minimum = 5;
    $scope.p.numeric_maximum = 11;
    var c = new Controller($scope);
    expect(c.getLimit()).toEqual('5 <= x <= 11');
  });

  it('returns only one if one numeric limit is set', function() {
    var $scope = makeScope();
    $scope.p.numeric_minimum = 5;
    var c = new Controller($scope);
    expect(c.getLimit()).toEqual('5 <= x');
  });
});
