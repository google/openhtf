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
 * Tests for the station data service.
 */

var angular = require('angular');
var mock = require('angular-mocks');
var StationDataService = require('./stationdata-service.js');
var proto = require('openhtf-proto').openhtf;

describe('StationDataService', function() {

  beforeEach(function() {
    jasmine.addMatchers(promiseUtils.jasmineMatchers);

    var m = angular.module('test', ['ngMock']);
    m.service('stationDataService', StationDataService);
    window.module('test');
  });

  it('Caches the stationdata', inject(function(stationDataService) {
    var data = stationDataService.getStationData('test');
    var data2 = stationDataService.getStationData('test');
    expect(data).toBe(data2);
  }));

  it('fetches data but rejects if none returned',
     inject(function(stationDataService, $httpBackend) {
    $httpBackend.expectGET('/api/stations/test').respond(200, '');
    var data = stationDataService.getStationData('test');
    var promise = data.updateData();
    $httpBackend.flush();
    expect(promise).toHaveBeenRejected();

    $httpBackend.verifyNoOutstandingExpectation();
    $httpBackend.verifyNoOutstandingRequest();
  }));

  it('fetches data and saves on success',
     inject(function(stationDataService, $httpBackend) {
    var p = new proto.HTFStationResponse();
    p.station_name = 'test me yep';
    var buffer = p.encode();

    $httpBackend.expectGET('/api/stations/test').respond(200, buffer.toBase64());
    var data = stationDataService.getStationData('test');
    var promise = data.updateData();
    $httpBackend.flush();
    expect(promise).toHaveBeenResolved();
    expect(data.getData()).toEqual(p);

    $httpBackend.verifyNoOutstandingExpectation();
    $httpBackend.verifyNoOutstandingRequest();
  }));

  it('handles rejection',
     inject(function(stationDataService, $httpBackend) {
    $httpBackend.expectGET('/api/stations/test').respond(500, 'you suck');
    var data = stationDataService.getStationData('test');
    var promise = data.updateData();
    $httpBackend.flush();
    expect(promise).toHaveBeenRejectedWith('you suck');

    $httpBackend.verifyNoOutstandingExpectation();
    $httpBackend.verifyNoOutstandingRequest();
  }));
});
