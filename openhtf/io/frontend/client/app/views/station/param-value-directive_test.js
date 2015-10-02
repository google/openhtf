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

var directive = require('./param-value-directive.js');
var proto = require('openhtf-proto').openhtf;

describe('ParamValueDirective', function() {
  function makeScope() {
    var p = new proto.TestParameter();
    return {
      parameter: function() { return this.realparameter; },
      realparameter: p
    };
  }
  var Controller = directive().controller;

  it('returns empty if nothing set', function() {
    var $scope = makeScope();
    var c = new Controller($scope);
    expect(c.getValue()).toEqual('');
  });

  it('returns text value if set', function() {
    var $scope = makeScope();
    $scope.realparameter.text_value = 'hi';
    var c = new Controller($scope);
    expect(c.getValue()).toEqual('hi');
  });

  it('returns numeric value if set or both set', function() {
    var $scope = makeScope();
    $scope.realparameter.numeric_value = 3;
    var c = new Controller($scope);
    expect(c.getValue()).toEqual(3);

    $scope.realparameter.text_value = 'hi';
    expect(c.getValue()).toEqual(3);
  });
});
