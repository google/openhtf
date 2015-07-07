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
 * @fileoverview A simple filter to convert a millis timestamp to seconds.
 */

var angular = require('angular');

/** Converts milliseconds to seconds. */
function MillisToSeconds(input) {
  if (!angular.isNumber(input)) {
    return input;
  }
  return parseInt(input / 1000);
}

/**
 * Registers a filter which takes the number of seconds and transforms it into a
 * duration string.
 *
 * @param {!angular.Module} app The angular app with which to register.
 */
function MillisDuration($interpolate, input) {
  var seconds = MillisToSeconds(input);
  var divisions = [
    ['{{amount}} hour{{multi}}', 60 * 60, Math.floor],
    ['{{amount}} min{{multi}}', 60, Math.floor],
    ['{{amount}} sec{{multi}}', 1, angular.identity]
  ];

  var result = [];
  for (var d = divisions.shift(); d; d = divisions.shift()) {
    var amount = d[2](seconds / d[1]);
    seconds = seconds % d[1];

    if (amount > 0) {
      var exp = $interpolate(d[0]);
      result.push(exp({amount: amount, multi: (amount > 1 ? 's' : '')}));
    }
  }

  return result.join(' ');
}

var m = module.exports =
    angular.module('openhtf.components.filters.timestamp', []);
m.filter('millisToSeconds', function() { return MillisToSeconds; });
m.filter('millisDuration', function($interpolate) { return MillisDuration.bind(null, $interpolate); });
