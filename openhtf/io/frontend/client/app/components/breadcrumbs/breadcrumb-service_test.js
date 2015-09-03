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
 * Tests for the breadcrumb service.
 */

var BreadcrumbService = require('./breadcrumb-service.js');

describe('BreadcrumbService', function() {
  it('clears breadcrumbs', function() {
    var bs = new BreadcrumbService();
    bs.pushBreadcrumb('hi');
    bs.clear();
    expect(bs.getBreadcrumbString()).toEqual('');
  });

  it('pushes and pops a breadcrumb off', function() {
    var bs = new BreadcrumbService();
    bs.pushBreadcrumb('hi');
    bs.pushBreadcrumb('there');
    expect(bs.getBreadcrumbString()).toEqual('hi > there');
    bs.popBreadcrumb();
    expect(bs.getBreadcrumbString()).toEqual('hi');
  });

  it("doesn't error if popped empty", function() {
    var bs = new BreadcrumbService();
    bs.popBreadcrumb();
    expect(bs.getBreadcrumbString()).toEqual('');
  });
});
