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
