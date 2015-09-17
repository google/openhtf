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

var m = module.exports = angular.module('openhtf', [
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

  $stateProvider.state('openhtf', {
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
