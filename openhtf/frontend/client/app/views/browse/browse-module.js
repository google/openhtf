/**
 * @fileoverview The top-level module for the browse page.
 */

var angular = require('angular');
var routerModuleName = require('angular-ui-router');

var contentTemplate = require('./browse.content.html');
var breadcrumbs = require('../../components/breadcrumbs/breadcrumb-module.js');
var api = require('../../components/api/api-module.js');
var starred = require('../../components/starred/starred-module.js');
var PollMode = require('../../components/api/poller-factory.js').PollMode;

var stationlist = require('./stationlist-directive.js');

var m = module.exports = angular.module('openhtf.views.browse', [
  contentTemplate.name,
  routerModuleName,
  api.name,
  starred.name,
  breadcrumbs.name,
  stationlist.name,
]);

/** Configures the browse stations view. */
m.config(function($stateProvider) {
  $stateProvider.state('openhtf.browse', {
    url: '/browse',
    views: {'content@': {templateUrl: 'browse.content.html'}},
    onEnter: function(oxBreadcrumbService, stationsServicePoller) {
      oxBreadcrumbService.pushBreadcrumb('Browse Stations');
      stationsServicePoller.setPollMode(PollMode.INTERACTIVE);
    },
    onExit: function(oxBreadcrumbService, stationsServicePoller) {
      oxBreadcrumbService.popBreadcrumb();
      stationsServicePoller.setPollMode(PollMode.BACKGROUND);
    }
  });
});
