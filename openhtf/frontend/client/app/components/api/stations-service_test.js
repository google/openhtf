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
