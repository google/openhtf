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
 * Tests for the poller factory.
 */

var angular = require('angular');
var angularmocks = require('angular-mocks');
var polling = require('./poller-factory.js');

describe('PollService', function() {
  beforeEach(function() {
    var m = angular.module('test', ['ngMock']);
    m.factory('pollerFactory', function($timeout, $log) {
      return new polling.PollFactory($timeout, $log);
    });
    window.module('test');
  });

  it('polls on instantiation', inject(function(pollerFactory) {
    var spy = promiseUtils.createSpyReturningPromise('handler');
    var poller = pollerFactory.create(spy);
    expect(spy.calls.count()).toEqual(1);
  }));

  it('schedules polling', inject(function(pollerFactory, $timeout) {
    var spy = promiseUtils.createSpyReturningPromise('handler');
    var poller = pollerFactory.create(spy);
    spy.resolveResult();

    poller.schedulePoll();
    $timeout.flush(10050);
    expect(spy.calls.count()).toEqual(2);
    spy.resolveResult();

    $timeout.flush(20100);
    expect(spy.calls.count()).toEqual(3);
  }));

  it('changes modes and polls fasta', inject(function(pollerFactory, $timeout) {
    var spy = promiseUtils.createSpyReturningPromise('handler');
    var poller = pollerFactory.create(spy);
    spy.resolveResult();

    poller.schedulePoll();
    poller.setPollMode(polling.PollMode.INTERACTIVE);
    $timeout.flush(10050);
    expect(spy.calls.count()).toEqual(2);
    spy.resolveResult();

    $timeout.flush(13000);
    expect(spy.calls.count()).toEqual(3);
  }));

  it('schedule returns existing promise', inject(function(pollerFactory, $timeout) {
    var spy = promiseUtils.createSpyReturningPromise('handler');
    var poller = pollerFactory.create(spy);
    spy.resolveResult();

    var p = poller.schedulePoll();
    var pnext = poller.schedulePoll();
    expect(p).toBe(pnext);
  }));
});
