/**
 * @fileoverview A module for handling breadcrumbs.
 */

var angular = require('angular');
var BreadcrumbService = require('./breadcrumb-service.js');
var BreadcrumbDirective = require('./breadcrumb-directive.js');
var template = require('./breadcrumb.html');

var m = module.exports =
    angular.module('oxc.components.breadcrumbs', [template.name]);
m.service('oxBreadcrumbService', BreadcrumbService);
m.directive('oxBreadcrumbs', BreadcrumbDirective);
