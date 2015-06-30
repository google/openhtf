/**
 * @fileoverview A Client javascript.
 */
var angular = require('angular');
var routerModuleName = require('angular-ui-router');

// Views
var browse = require('./views/browse/browse-module.js');
var station = require('./views/station/station-module.js');

// Components
var breadcrumbs = require('./components/breadcrumbs/breadcrumb-module.js');
var api = require('./components/api/api-module.js');
var starred = require('./components/starred/starred-module.js');
var STARLIST_CHANGED_EVENT = require(
    './components/starred/starredstations-directive.js').STARLIST_CHANGED_EVENT;

var m = module.exports = angular.module('oxc', [
  routerModuleName,
  api.name,
  starred.name,
  browse.name,
  station.name,
  breadcrumbs.name
]);

/**
 * Configures the base oxc module.
 */
m.config(function($locationProvider, $urlRouterProvider, $stateProvider) {
  $locationProvider.html5Mode(true);
  $urlRouterProvider.when('/', '/browse');

  $stateProvider.state('oxc', {
    abstract: true,
    onEnter: function(oxBreadcrumbService) {
      oxBreadcrumbService.clear();
      oxBreadcrumbService.pushBreadcrumb('Home', '/');
    }
  });
});

/**
 * A small app level directive to handle our fixed footer.
 */
m.directive('oxFooterFix', function($document, starService) {
  return {
    restrict: 'A',
    link: function($scope, $element, $attrs) {
      var footer = $document[0].getElementById('starredStations');
      $scope.$on(STARLIST_CHANGED_EVENT, function() {
        $element[0].style.paddingBottom =
            (footer.getBoundingClientRect().height + 20) + 'px';
      });
    }
  };
});
