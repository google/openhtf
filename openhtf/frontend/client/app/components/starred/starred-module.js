/**
 * @fileoverview The starred footer module.
 */

var angular = require('angular');
var directive = require('./starredstations-directive.js');
var StarService = require('./star-service.js');
var directiveTemplate = require('./starredstations.html');

var m = module.exports = angular.module('oxc.components.starred', [
    directiveTemplate.name]);
m.directive('oxStarredStations', directive.StarredStations);
m.service('starService', StarService);
