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
