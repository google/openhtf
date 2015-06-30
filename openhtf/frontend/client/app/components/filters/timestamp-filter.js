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
    angular.module('oxc.components.filters.timestamp', []);
m.filter('millisToSeconds', function() { return MillisToSeconds; });
m.filter('millisDuration', function($interpolate) { return MillisDuration.bind(null, $interpolate); });
