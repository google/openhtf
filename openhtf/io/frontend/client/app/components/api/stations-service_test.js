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
 * Tests for the station service.
 */

var angular = require('angular');
var angularmocks = require('angular-mocks');
var service = require('./stations-service.js');

describe('StationService', function() {
  beforeEach(function() {
    angular.module('test', ['ngMock'])
        .service('stationsService', service.StationService);
    window.module('test');
  });

  afterEach(inject(function($httpBackend) {
    $httpBackend.verifyNoOutstandingExpectation();
    $httpBackend.verifyNoOutstandingRequest();
  }));

  it('fetches the station list', inject(function($httpBackend, stationsService) {
    $httpBackend.expectGET('/api/stations').respond(200, {
      'one.station': 'RUNNING',
      'two.station': 'OFFLINE',
      'three.station': 'SOMETHING'
    });

    var promise = stationsService.fetchStationsNow();
    expect(stationsService.isFetching).toBeTruthy();
    $httpBackend.flush();

    expect(stationsService.getStations()[0]).toEqual({
      stationName: 'one.station', state: service.StationState.RUNNING });
    expect(stationsService.getStations()[1]).toEqual({
      stationName: 'three.station', state: service.StationState.UNKNOWN });
    expect(stationsService.getStations()[2]).toEqual({
      stationName: 'two.station', state: service.StationState.OFFLINE });
  }));
});
