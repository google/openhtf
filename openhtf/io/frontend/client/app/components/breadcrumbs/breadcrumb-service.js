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
 * @fileoverview A service for stashing the current breadcrumbs.
 *
 * It's not a very complicated service, it expects the different places to
 * set their own fully qualified breadcrumbs and does no tracking.
 */

function BreadcrumbService() {
  this.breadcrumbs = [];
}

/** Clears the list of breadcrumbs completely. */
BreadcrumbService.prototype.clear = function() {
  this.breadcrumbs = [];
};

/** Pops a breadcrumb off of the end. */
BreadcrumbService.prototype.popBreadcrumb = function() {
  this.breadcrumbs.pop();
};

/** Pushes a breadcrumb onto the stack. */
BreadcrumbService.prototype.pushBreadcrumb = function(breadcrumb, opt_link) {
  this.breadcrumbs.push({ text: breadcrumb, link: opt_link });
};

/** Retrieves a breadcrumb string. */
BreadcrumbService.prototype.getBreadcrumbs = function() {
  return this.breadcrumbs;
};

module.exports = BreadcrumbService;
