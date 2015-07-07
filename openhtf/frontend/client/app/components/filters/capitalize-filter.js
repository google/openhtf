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
 * @fileoverview A filter to capitalize strings.
 */

var angular = require('angular');

/**
 * Capitalizes text in a string.
 * @param {string} input The text to capitalize
 * @return {string} A string with the first letter capitalized.
 */
function Capitalize(input) {
  if (!angular.isString(input) || !input.length) {
    return input;
  }
  return input[0].toUpperCase() + input.substr(1).toLowerCase();
}

var m = module.exports = angular.module(
    'openhtf.components.filters.capitalize', []);
m.filter('capitalize', function() { return Capitalize; });
