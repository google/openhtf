/**
 * Tests for the station content controller
 */

var angular = require('angular');
require('angular-mocks');
var proto = require('openhtf-proto').openhtf;
var Controller = require('./stationcontent-controller.js');

describe('ContentController', function() {

  beforeEach(function() {
    var m = angular.module('test', []);
    m.service('stationData', function() {
      var resp = this.response = new proto.HTFStationResponse();
      var cell = this.cell = new proto.HTFCell();
      cell.cell_number = 1;
      resp.cells.push(cell);
      this.getData = function() { return this.response; };
    });
    window.module('test');
  });

  function TP(name, param_status, opt_important) {
    var tp = new proto.TestParameter();
    tp.name = name;
    tp.status = param_status;
    tp.important = !!opt_important;
    return tp;
  }

  it('returns false with no testrun', inject(function($rootScope, stationData) {
    var c = new Controller($rootScope, stationData, 1);
    expect(c.hasTestRun()).toBeFalsy();
  }));

  it('returns true if it has a testrun.',
     inject(function($rootScope, stationData) {
       var c = new Controller($rootScope, stationData, 1);
       stationData.cell.test_run = new proto.TestRun();
       expect(c.hasTestRun()).toBeTruthy();
     }));

  it('correctly returns test status', inject(function($rootScope, stationData) {
    var c = new Controller($rootScope, stationData, 1);
    var tr = stationData.cell.test_run = new proto.TestRun();
    tr.test_status = proto.Status.PASS;
    expect(c.isFinished()).toBeTruthy();

    tr.test_status = proto.Status.RUNNING;
    expect(c.isFinished()).toBeFalsy();
  }));

  it('Sorts test parameters into groups',
     inject(function($rootScope, stationData) {
       var c = new Controller($rootScope, stationData, 1);
       var tr = stationData.cell.test_run = new proto.TestRun();
       tr.test_parameters.push(TP('pass', proto.Status.PASS));
       tr.test_parameters.push(TP('important', proto.Status.FAIL, true));
       tr.test_parameters.push(TP('unset', proto.Status.ERROR));
       tr.test_parameters.push(TP('fail', proto.Status.FAIL));
       $rootScope.$digest();
       expect(c.parameters.length).toEqual(4);
     }));

  it('skips missing groups', inject(function($rootScope, stationData) {
    var c = new Controller($rootScope, stationData, 1);
    var tr = stationData.cell.test_run = new proto.TestRun();
    tr.test_parameters.push(TP('pass', proto.Status.PASS));
    tr.test_parameters.push(TP('unset', proto.Status.ERROR));
    tr.test_parameters.push(TP('fail', proto.Status.FAIL));
    $rootScope.$digest();
    expect(c.parameters.length).toEqual(3);
  }));

  it('handles no parameters', inject(function($rootScope, stationData) {
    var c = new Controller($rootScope, stationData, 1);
    $rootScope.$digest();
    expect(c.parameters.length).toEqual(0);
  }));

  it('Calculates the duration', inject(function($rootScope, stationData) {
    var c = new Controller($rootScope, stationData, 1);
    var tr = stationData.cell.test_run = new proto.TestRun();
    tr.end_time_millis = 5000;
    tr.start_time_millis = 1000;
    expect(c.getTestDuration()).toEqual(4000);
  }));

  it('Uses the right cell', inject(function($rootScope, stationData) {
    var cell = new proto.HTFCell();
    stationData.response.cells.push(cell);
    var tr = cell.test_run = new proto.TestRun();

    var c = new Controller($rootScope, stationData, 1);
    expect(c.hasTestRun()).toBeFalsy();

    c = new Controller($rootScope, stationData, 2);
    expect(c.hasTestRun()).toBeTruthy();
  }));
});
