/**
 * @fileoverview The top-level module for the history page.
 */

var angular = require('angular');
var template = require('./history-content.html');
var routerModuleName = require('angular-ui-router');

var breadcrumbs = require(
    '../../../components/breadcrumbs/breadcrumb-module.js');

var m = module.exports = angular.module('openhtf.views.station.history', [
    template.name, routerModuleName, breadcrumbs.name]);

/** Configures the browse stations view. */
m.config(function($stateProvider) {
  $stateProvider.state('openhtf.station.history', {
    url: '/history',
    views: {
      'content@': {
        templateUrl: 'history-content.html'
      }
    },
    onEnter: function(oxBreadcrumbService) {
      oxBreadcrumbService.pushBreadcrumb('History');
    },
    onExit: function(oxBreadcrumbService) {
      oxBreadcrumbService.popBreadcrumb();
    }
  });
});


