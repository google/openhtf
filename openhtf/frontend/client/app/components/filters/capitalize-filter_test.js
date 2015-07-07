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
 * Tests for the capitalize filter.
 */

var angular = require('angular');
var angularmock = require('angular-mocks');
var capitalize = require('./capitalize-filter.js');

describe('Capitalize', function() {
  beforeEach(function() {
    window.module(capitalize.name);
  });

  it('capitalizes the word', inject(function(capitalizeFilter) {
    expect(capitalizeFilter('hello there')).toEqual('Hello there');
  }));
});
