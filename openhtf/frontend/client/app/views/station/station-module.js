/**
 * @fileoverview The top-level module for the station page.
 */

var angular = require('angular');
var routerModuleName = require('angular-ui-router');
var angularMoment = require('angular-moment');

var template = require('./station.content.html');
var history = require('./history/history-module.js');

var breadcrumbs = require('../../components/breadcrumbs/breadcrumb-module.js');
var capitalize = require('../../components/filters/capitalize-filter.js');
var millisToSeconds = require('../../components/filters/timestamp-filter.js');
var api = require('../../components/api/api-module.js');
var PollMode = require('../../components/api/poller-factory.js').PollMode;

var ContentController = require('./stationcontent-controller.js');
var ParamStatusDirective = require('./param-status-directive.js');
var ParamValueDirective = require('./param-value-directive.js');
var ParamLimitDirective = require('./param-limit-directive.js');

var m = module.exports = angular.module('openhtf.views.station', [
  api.name,
  history.name,
  template.name,
  routerModuleName,
  breadcrumbs.name,
  capitalize.name,
  millisToSeconds.name,
  'angularMoment',
]);

/** Configures the browse stations view. */
m.config(function($stateProvider, $urlRouterProvider) {
  $urlRouterProvider.when('/station/{station}', '/station/{station}/1');

  $stateProvider.state('openhtf.station', {
    url: '/station/{station}',
    resolve: {
      stationName: function($stateParams) {
        return $stateParams.station;  // comes from the parent
      },
      stationData: function(stationName, stationDataService) {
        return stationDataService.getStationData(stationName);
      },
      stationDataLoaded: function(stationData) {
        return stationData.updateData();
      },
      // A poller which refreshes station data interactively until we leave this
      // page.  This keeps the station information up to date.
      stationPoller: function(stationData, stationName, pollerFactory) {
        var poller = pollerFactory.create(
            stationData.updateData.bind(stationData), stationName);
        poller.setPollMode(PollMode.INTERACTIVE);
        return poller;
      }
    },
    onEnter: function(oxBreadcrumbService, stationName, capitalizeFilter, $state) {
      // Add the cell # we're viewing
      oxBreadcrumbService.pushBreadcrumb(capitalizeFilter(stationName));
    },
    onExit: function(oxBreadcrumbService, stationPoller) {
      oxBreadcrumbService.popBreadcrumb();
      stationPoller.stop();
    },
    abstract: true,
  });

  $stateProvider.state('openhtf.station.cell', {
    url: '/{cell:int}',
    resolve: {
      cellNumber: function($stateParams) {
        return $stateParams.cell;
      }
    },
    onEnter: function(oxBreadcrumbService, cellNumber) {
      oxBreadcrumbService.pushBreadcrumb('Cell #' + cellNumber);
    },
    onExit: function(oxBreadcrumbService, cellNumber) {
      oxBreadcrumbService.popBreadcrumb();
    },
    views: {'content@': {
      templateUrl: 'station.content.html',
      controller: ContentController,
      controllerAs: 'CC'
    }}
  });
});

m.directive('oxParamStatus', ParamStatusDirective);
m.directive('oxParamValue', ParamValueDirective);
m.directive('oxParamLimit', ParamLimitDirective);
