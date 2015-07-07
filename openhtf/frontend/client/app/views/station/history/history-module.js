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


